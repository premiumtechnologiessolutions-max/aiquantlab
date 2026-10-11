# AI QUANT LAB — PROJECT CONSTITUTION

## 1. الهدف الرئيسي

بناء مختبر كمي ذاتي التشغيل يعتمد على فريق من AI Agents، مهمته:

* دراسة أزواج الفوركس.
* اكتشاف حالات السوق المختلفة.
* تجربة الخوارزميات والاستراتيجيات.
* إجراء Backtesting عميق.
* معرفة الاستراتيجية المناسبة لكل زوج ولكل فترة زمنية.
* اكتشاف وقت بداية ونهاية كل Market Regime.
* تطوير الاستراتيجيات والنماذج باستمرار.
* إصدار نتائج وتقارير قابلة للتدقيق.

## 2. نطاق النسخة الأولى

تبدأ النسخة الأولى بالأزواج الأساسية التالية:

* EURUSD
* GBPUSD
* USDJPY
* USDCHF
* USDCAD
* AUDUSD
* NZDUSD

الأطر الزمنية الأولى:

* M5
* M15
* H1

بعد نجاح النظام، تتم إضافة باقي الأزواج والفريمات.

## 3. وضع التشغيل الأول

النسخة الأولى هي:

* Research Only
* Backtesting
* Shadow Trading
* Paper Trading
* اتصال وتنفيذ محدود على حساب MT5 Demo فقط

يُمنع التداول بأموال حقيقية خلال مرحلة البناء والاختبار.
يُرفض أي حساب MT5 حقيقي أو Contest برمجيًا قبل التنفيذ.

## 4. أنواع الاستراتيجيات

يجب أن يدعم النظام على الأقل:

* Trend Following
* Momentum
* Breakout
* Mean Reversion
* Volatility Trading
* Statistical Models
* Market Regime Detection
* Change-Point Detection
* News and Macro Analysis
* Machine Learning
* Online Learning
* Mixture of Experts

## 5. نظام التعلم

يجب أن يتعلم النظام:

* خصائص كل زوج بشكل منفصل.
* الأنماط المشتركة بين جميع الأزواج.
* أفضل استراتيجية لكل Market Regime.
* أفضل استراتيجية لكل ساعة وجلسة تداول.
* متى تبدأ أفضلية الاستراتيجية.
* متى تنتهي أو تضعف.
* تأثير الأخبار والسبريد والتذبذب.
* الفرق بين نتائج Backtest والأداء الحقيقي التجريبي.

## 6. قواعد الاختبار

لا تُقبل أي استراتيجية قبل اجتياز:

* Out-of-Sample Testing
* Walk-Forward Testing
* Spread and Slippage Testing
* Monte Carlo Testing
* Parameter Stability Testing
* Overfitting Detection
* Look-Ahead Bias Detection
* Data Leakage Detection
* Shadow Trading
* Paper Trading

## 7. معايير تقييم الاستراتيجيات

لا يتم التقييم حسب الربح فقط، بل حسب:

* Net Profit After Costs
* Maximum Drawdown
* Sharpe Ratio
* Sortino Ratio
* Profit Factor
* Expected Value
* Number of Trades
* Performance Stability
* Parameter Stability
* Performance Across Years
* Performance Across Market Regimes
* Probability of Overfitting

## 8. صلاحيات الـAgents

يسمح للـAgents بـ:

* كتابة الكود داخل بيئة البحث.
* إنشاء الاستراتيجيات.
* تشغيل الاختبارات.
* تحليل الأخطاء.
* اقتراح تحسينات.
* إنشاء نسخ تجريبية جديدة.
* مقارنة Champion وChallengers.
* مراقبة الأسعار على حساب Demo وتسجيل Shadow/Paper decisions.

يُمنع عليهم:

* التداول المباشر بأموال حقيقية.
* تغيير الحد الأقصى للمخاطرة.
* حذف التجارب الفاشلة.
* تعديل بيانات الاختبار بعد رؤية النتائج.
* ترقية نموذج إلى Live تلقائيًا.
* تعطيل نظام الحماية.
* زيادة حجم المخاطرة لتعويض الخسائر.
* إرسال أمر Broker تلقائيًا من إشارة استراتيجية.
* قبول حساب MT5 غير Demo.

يسمح بأمر MT5 Demo يدوي فقط بعد تفعيل منفصل، تأكيد بشري صريح، Stop Loss،
Take Profit، وحدود حجم وSpread وQuote age، ونجاح order_check.

## 9. مبدأ التطوير

كل نسخة جديدة يجب أن تمر بالتسلسل التالي:

Research
→ Coding
→ Automated Testing
→ Backtesting
→ Independent Validation
→ Shadow Trading
→ Paper Trading
→ Human Approval

## 10. المبدأ النهائي

هدف النظام ليس إيجاد صفقة مضمونة أو استراتيجية واحدة تعمل دائمًا.

هدفه اكتشاف:

* أي استراتيجية تعمل.
* على أي زوج.
* في أي وقت.
* تحت أي Market Regime.
* ووقت توقف أفضليتها.

كل قرار يجب أن يكون مسجلًا، قابلًا للتفسير، وقابلًا للرجوع إلى نسخة سابقة.
