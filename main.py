import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright
from openai import OpenAI
import requests

# ==================== 写死配置（直接使用 DeepSeek Key） ====================
OPENAI_API_KEY = "sk-34e74ea0e5e14100b7380a05ab67d400"
OPENAI_BASE_URL = "https://api.deepseek.com"
MODEL_TEXT = "deepseek-chat"
WECOM_WEBHOOK = ""
TARGET_URLS = [
    "https://example.com/product/123",
    "https://example.com/product/456",
]
HISTORY_FILE = "history.json"
PRICE_DROP_ALERT_PERCENT = 0.15
SENTIMENT_SHIFT_THRESHOLD = 0.3

# ==================== Agent 1: 感知Agent ====================
class PerceptionAgent:
    def __init__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)

    def capture(self, url):
        print(f"[感知Agent] 正在抓取: {url}")
        page = self.browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        try:
            page.wait_for_selector("img", timeout=5000)
        except:
            pass
        body_text = page.inner_text("body")
        title = page.title()
        page.close()
        print(f"[感知Agent] ✅ 完成，标题: {title}，提取文本 {len(body_text)} 字符")
        return {"url": url, "title": title, "body_text": body_text[:6000]}

    def close(self):
        self.browser.close()
        self.playwright.stop()

# ==================== Agent 2: 解析Agent（纯文本，不传图片） ====================
class ParsingAgent:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    def parse(self, raw_data):
        print("[解析Agent] 正在用 DeepSeek 分析页面文本...")
        prompt = f"""你是一个电商数据提取器。根据以下网页文本，提取商品信息，返回JSON格式。

网页标题：{raw_data['title']}
网页文本：
{raw_data['body_text']}

请返回如下JSON（只返回JSON，不要其他内容）：
{{"product_name": "商品名称", "current_price": 数字, "original_price": 数字或null, "promotion_text": "促销文案", "is_new_arrival": true或false, "recent_reviews_summary": "评价情感倾向及关键词"}}

如果找不到某项信息，用null或"N/A"填充。"""

        response = self.client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000
        )
        content = response.choices[0].message.content
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            parsed = json.loads(content)
        except:
            parsed = {"error": "JSON解析失败", "raw": content}
        print(f"[解析Agent] ✅ 解析完成: {parsed.get('product_name', 'N/A')}, 价格: {parsed.get('current_price')}")
        return parsed

# ==================== Agent 3: 分析决策Agent ====================
class AnalysisAgent:
    def __init__(self):
        self.history_path = HISTORY_FILE
        if not os.path.exists(self.history_path):
            with open(self.history_path, 'w') as f:
                json.dump({}, f)

    def analyze(self, url, data):
        print("[分析Agent] 长链推理...")
        with open(self.history_path, 'r') as f:
            history = json.load(f)
        prev = history.get(url)
        alerts = []
        reasoning = []

        if prev and data.get("current_price") and prev.get("current_price"):
            change = (data["current_price"] - prev["current_price"]) / prev["current_price"]
            if change <= -PRICE_DROP_ALERT_PERCENT:
                alerts.append({"level": "high", "type": "sharp_price_drop", "detail": f"骤降{abs(change)*100:.1f}%"})
                reasoning.append(f"价格从{prev['current_price']}降至{data['current_price']}")
            elif change < 0:
                alerts.append({"level": "low", "type": "minor_price_drop"})
                reasoning.append(f"微降{abs(change)*100:.1f}%")
            elif change > 0.1:
                alerts.append({"level": "info", "type": "price_increase"})
        elif data.get("current_price"):
            reasoning.append("建立价格基线")

        if data.get("is_new_arrival") and (not prev or not prev.get("is_new_arrival")):
            alerts.append({"level": "medium", "type": "new_product_launch", "detail": "新品标记出现"})
            reasoning.append("新品角标识别")

        curr_senti = data.get("recent_reviews_summary", "")
        prev_senti = prev.get("recent_reviews_summary", "") if prev else ""
        if "负面" in curr_senti and "负面" not in prev_senti:
            alerts.append({"level": "high", "type": "negative_sentiment_surge"})
            reasoning.append("评价情感转负面")

        if prev and data.get("promotion_text") != prev.get("promotion_text"):
            alerts.append({"level": "medium", "type": "promotion_change"})
            reasoning.append("促销文案变更")

        history[url] = {
            "current_price": data.get("current_price"),
            "promotion_text": data.get("promotion_text"),
            "is_new_arrival": data.get("is_new_arrival"),
            "recent_reviews_summary": data.get("recent_reviews_summary"),
            "timestamp": datetime.now().isoformat()
        }
        with open(self.history_path, 'w') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        print(f"[分析Agent] ✅ {len(alerts)}条预警，推理链{reasoning}")
        return {"alerts": alerts, "reasoning": reasoning, "current_data": data}

# ==================== Agent 4: 报告生成Agent ====================
class ReportAgent:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def generate_and_push(self, url, analysis):
        print("[报告Agent] 生成情报卡片...")
        data = analysis["current_data"]
        alerts = analysis["alerts"]
        alert_block = ""
        for a in alerts:
            icon = "🔴" if a['level'] == 'high' else "🟡" if a['level'] == 'medium' else "🔵"
            alert_block += f"{icon} **{a['type']}**\n"
        if not alert_block:
            alert_block = "✅ 无预警"

        markdown = f"""## 🕵️ 竞品情报速报
**商品**：{data.get('product_name', url)}
**价格**：{data.get('current_price', 'N/A')}
**促销**：{data.get('promotion_text', '无')}
**新品**：{'🚀新品' if data.get('is_new_arrival') else '正常'}
**评价**：{data.get('recent_reviews_summary', '无')}
### 预警中心
{alert_block}
> 推理：{' → '.join(analysis['reasoning'])}
> 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        print(markdown)
        if self.webhook_url:
            try:
                requests.post(self.webhook_url, json={"msgtype": "markdown", "markdown": {"content": markdown}}, timeout=10)
            except Exception as e:
                print(f"[报告Agent] 推送异常: {e}")

# ==================== 主流程 ====================
def main():
    print("🚀 AutoCompetitor 启动")
    p_agent = PerceptionAgent()
    parse_agent = ParsingAgent()
    analysis_agent = AnalysisAgent()
    report_agent = ReportAgent(WECOM_WEBHOOK)

    for url in TARGET_URLS:
        try:
            raw = p_agent.capture(url)
            parsed = parse_agent.parse(raw)
            analysis = analysis_agent.analyze(url, parsed)
            report_agent.generate_and_push(url, analysis)
        except Exception as e:
            print(f"❌ {url} 错误: {e}")
        print("=" * 50)

    p_agent.close()
    print("🏁 监控完成")

if __name__ == "__main__":
    main()