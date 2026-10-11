from __future__ import annotations

from ai_quant_lab.agents.conversation import AgentConversationService
from ai_quant_lab.model_config import load_model_runtime
from ai_quant_lab.runtime import LabRuntime

EXIT_COMMANDS = frozenset(
    {
        "exit",
        "quit",
        "close",
        "خروج",
        "سكر",
        "إغلاق",
        "اغلاق",
    }
)


def normalize_command(value: str) -> str:
    """Normalize a command for reliable comparison."""

    return " ".join(
        value.strip().casefold().split(),
    )


def main() -> None:
    """Run an interactive text conversation with the agent team."""

    runtime = LabRuntime()
    runtime.start()
    model_runtime = load_model_runtime()
    conversation = AgentConversationService(
        runtime,
        profiles=model_runtime.profiles,
        providers=model_runtime.providers,
    )

    print()
    print("AI Quant Lab Agent Console")
    print("=" * 32)
    print("نادِ أي Agent باسمه واسأله شو عم يعمل.")
    print("اكتب «مساعدة» لعرض الأوامر.")
    print("اكتب «خروج» لإغلاق المحادثة.")
    print()

    while True:
        try:
            user_text = input("أنت: ")
        except (EOFError, KeyboardInterrupt):
            print()
            print("Atlas: تم إغلاق المحادثة بأمان.")
            break

        if normalize_command(user_text) in EXIT_COMMANDS:
            print("Atlas: تم إغلاق المحادثة بأمان.")
            break

        result = conversation.ask(user_text)

        print()
        print(result.reply)
        print()

    runtime.stop()


if __name__ == "__main__":
    main()
