from __future__ import annotations

from collections import deque
from itertools import count
from threading import RLock
from typing import Protocol

from ai_quant_lab.agents.console import AgentConsole, AgentConsoleResult
from ai_quant_lab.agents.identifiers import normalize_spoken_text
from ai_quant_lab.modeling import (
    AgentModelProfile,
    ModelProviderRegistry,
    ModelProviderUnavailable,
    ModelRequest,
)
from ai_quant_lab.runtime.lab import LabRuntime


class AgentContextProvider(Protocol):
    """Optional local facts supplied by market, account, or experiment services."""

    def answer(self, agent_key: str, user_text: str) -> str | None:
        """Return a factual direct answer when the question matches local state."""

        ...  # pragma: no cover

    def context(self, agent_key: str) -> str:
        """Return concise local facts suitable for an optional model prompt."""

        ...  # pragma: no cover


class AgentConversationService:
    """Route user questions through persisted tasks, messages, and journals."""

    _WHY_FOLLOW_UPS = frozenset({"ليش", "لماذا", "why", "why so"})
    _NEXT_FOLLOW_UPS = frozenset(
        {"وبعدين", "بعدين", "شو بعد", "شو الخطوة الجاية", "what next", "then what"}
    )
    _REPEAT_FOLLOW_UPS = frozenset({"عيد", "عيدها", "كرر", "كررها", "say again", "repeat"})

    def __init__(
        self,
        runtime: LabRuntime,
        *,
        profiles: tuple[AgentModelProfile, ...] = (),
        providers: ModelProviderRegistry | None = None,
        context_provider: AgentContextProvider | None = None,
    ) -> None:
        self.runtime = runtime
        self.console = AgentConsole(runtime.team)
        self.profiles = {profile.agent_key: profile for profile in profiles}
        self.providers = providers or ModelProviderRegistry()
        self.context_provider = context_provider
        self._request_counter = count(1)
        self._active_agent_key: str | None = None
        self._history: dict[str, deque[tuple[str, str]]] = {}
        self._lock = RLock()

    def ask(self, text: str) -> AgentConsoleResult:
        """Answer one user question and persist both sides of addressed chats."""

        original = text.strip()

        if not original:
            return self.console.handle(original)

        agent = self.runtime.team.resolve_agent(original)

        if agent is None:
            normalized = normalize_spoken_text(original)

            if normalized in {
                "شو عمل الفريق اليوم",
                "شو عملتوا اليوم",
                "daily report",
                "today report",
            }:
                return AgentConsoleResult(
                    input_text=original,
                    reply=self.runtime.journal.daily_summary(),
                )

            console_result = self.console.handle(original)

            if console_result.success:
                return console_result

            with self._lock:
                active_agent_key = self._active_agent_key

            if active_agent_key is None:
                return console_result

            agent = self.runtime.team.get_agent(active_agent_key)
        else:
            with self._lock:
                self._active_agent_key = agent.identity.key

        incoming = self.runtime.message_bus.send(
            sender_key="user",
            recipient_key=agent.identity.key,
            subject="User question",
            body=original,
        )
        self.runtime.message_bus.mark_read(
            incoming.message_id,
            reader_key=agent.identity.key,
        )

        reply = (
            self.context_provider.answer(agent.identity.key, original)
            if self.context_provider is not None
            else None
        )

        if reply is None:
            reply = self._model_reply(agent.identity.key, original)

        if reply is None:
            reply = self._truthful_runtime_reply(
                agent.identity.key,
                original,
                previous_reply=self._previous_reply(agent.identity.key),
            )

        self.runtime.message_bus.send(
            sender_key=agent.identity.key,
            recipient_key="user",
            subject="Agent reply",
            body=reply,
        )
        self._record_turn(agent.identity.key, original, reply)

        return AgentConsoleResult(
            input_text=original,
            reply=reply,
            matched_agent_key=agent.identity.key,
        )

    def _model_reply(
        self,
        agent_key: str,
        user_text: str,
    ) -> str | None:
        """Use an explicitly configured provider, otherwise remain deterministic."""

        profile = self.profiles.get(agent_key)

        if profile is None or profile.model is None:
            return None

        agent = self.runtime.team.get_agent(agent_key)
        request = ModelRequest(
            request_id=f"request_{next(self._request_counter):06d}",
            agent_key=agent_key,
            system_prompt=profile.system_prompt,
            user_prompt=user_text,
            context=(
                f"Current recorded status:\n{agent.status_reply()}\n\n"
                f"Current recorded tasks:\n{agent.tasks_reply()}\n\n"
                f"Current local facts:\n{self._local_context(agent_key)}"
                f"\n\nRecent conversation:\n{self._conversation_history(agent_key)}"
            ),
            allowed_tools=profile.permissions.allowed_tools,
            maximum_output_tokens=profile.model.maximum_output_tokens,
        )

        try:
            provider = self.providers.get(profile.model.provider_key)
            return provider.complete(request, profile.model).text
        except ModelProviderUnavailable:
            return None

    def _truthful_runtime_reply(
        self,
        agent_key: str,
        user_text: str,
        *,
        previous_reply: str | None,
    ) -> str:
        """Answer from real local state when no external AI is configured."""

        normalized = normalize_spoken_text(user_text).strip("؟?!.,،؛: ")
        agent = self.runtime.team.get_agent(agent_key)

        if normalized in self._REPEAT_FOLLOW_UPS and previous_reply is not None:
            return previous_reply

        if normalized in self._WHY_FOLLOW_UPS:
            return self._why_reply(agent_key, previous_reply)

        if normalized in self._NEXT_FOLLOW_UPS:
            return self._next_reply(agent_key, previous_reply)

        if any(word in normalized for word in ("اليوم", "today", "daily")):
            return f"{agent.identity.name}: {self.runtime.journal.daily_summary()}"

        if any(word in normalized for word in ("رسائل", "messages", "inbox")):
            unread = self.runtime.message_bus.inbox(agent_key, unread_only=True)

            return f"{agent.identity.name}: عندي {len(unread)} رسالة غير مقروءة."

        if agent_key == "atlas" and any(
            word in normalized for word in ("الفريق", "team", "التقدم", "التقدّم", "progress")
        ):
            return self.runtime.coordinator.progress_reply()

        return agent.tasks_reply()

    def _why_reply(self, agent_key: str, previous_reply: str | None) -> str:
        """Explain common status follow-ups without inventing an unrecorded cause."""

        name = self.runtime.team.get_agent(agent_key).identity.name

        if previous_reply is None:
            return f"{name}: خبرني شو الشي اللي بدك تعرف سببه."

        normalized_previous = normalize_spoken_text(previous_reply)

        if "مهمة" in normalized_previous and (
            "ما عندي" in normalized_previous or "ما في" in normalized_previous
        ):
            return (
                f"{name}: لأن لوحة المهام المشتركة ما فيها مهمة جديدة مسندة إلي هلق. "
                "فيك تضغط «شغّل دورة عمل» حتى Atlas يراجع الأعمال الجاهزة."
            )

        if "بعد ما في market scan" in normalized_previous:
            return (
                f"{name}: لأنه ما انحفظ فحص سوق ناجح بعد. "
                "اضغط «افحص السوق الآن» وبعدها اسألني من جديد."
            )

        if "مش موصول" in normalized_previous:
            return f"{name}: لأن اتصال MT5 Demo غير فعّال بحسب الحالة المسجّلة هلق."

        return (
            f"{name}: ما عندي سبب إضافي مسجّل وراء جوابي السابق. "
            "قل إذا قصدك سبب الإشارة، حالة السوق، الحساب، أو المهمة حتى أقرأ بياناته."
        )

    def _next_reply(self, agent_key: str, previous_reply: str | None) -> str:
        """Give a bounded next action based on the latest recorded reply."""

        name = self.runtime.team.get_agent(agent_key).identity.name
        normalized_previous = normalize_spoken_text(previous_reply or "")

        if "مهمة" in normalized_previous and (
            "ما عندي" in normalized_previous or "ما في" in normalized_previous
        ):
            return (
                f"{name}: الخطوة الجاية شغّل دورة عمل من اللوحة، "
                "وبعدها اسألني شو المهمة اللي استلمتها."
            )

        return (
            f"{name}: فيك تسألني عن المهمة الحالية، آخر فحص للسوق، "
            "حساب الـDemo، الصفقات، أو الاستراتيجيات."
        )

    def _record_turn(self, agent_key: str, user_text: str, reply: str) -> None:
        with self._lock:
            history = self._history.setdefault(agent_key, deque(maxlen=6))
            history.append((user_text, reply))

    def _previous_reply(self, agent_key: str) -> str | None:
        with self._lock:
            history = self._history.get(agent_key)
            return history[-1][1] if history else None

    def _conversation_history(self, agent_key: str) -> str:
        with self._lock:
            history = tuple(self._history.get(agent_key, ()))

        if not history:
            return "No earlier turn is available in this session."

        return "\n".join(f"User: {user_text}\nAgent: {reply}" for user_text, reply in history)

    def _local_context(self, agent_key: str) -> str:
        """Return bounded external local context without inventing state."""

        if self.context_provider is None:
            return "No additional local facts are available."

        return self.context_provider.context(agent_key)
