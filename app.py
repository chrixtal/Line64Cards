import os
from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, ImageSendMessage
from siliconflow import ImageGenerator
from kolor import ColorAdjuster
import tempfile
import requests

app = Flask(__name__)

# 從環境變數獲取配置
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
siliconflow_api_key = os.getenv('SILICONFLOW_API_KEY')
kolor_api_key = os.getenv('KOLOR_API_KEY')

# 初始化 API 客戶端
sf_generator = ImageGenerator(api_key=siliconflow_api_key)
kolor_adjuster = ColorAdjuster(api_key=kolor_api_key)

# 使用 Render.com 的持久化臨時目錄
TEMP_DIR = os.path.join(os.getenv('TMPDIR', '/tmp'), 'line-bot-images')
os.makedirs(TEMP_DIR, exist_ok=True)


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        app.logger.error(f"Webhook處理錯誤: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "success"})


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text = event.message.text

    if text.startswith("生成 "):
        prompt = text[3:]
        try:
            # 生成圖片
            image = sf_generator.generate(prompt=prompt, size="1024x1024")
            temp_path = os.path.join(TEMP_DIR, f"generated_{event.message_id}.png")
            image.save(temp_path)

            # 色彩處理
            processed_path = process_with_kolor(temp_path)

            # 回傳圖片
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(
                    original_content_url=get_public_url(processed_path),
                    preview_image_url=get_public_url(processed_path)
                )
            )
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextMessage(text=f"生成失敗: {str(e)}")
            )


def process_with_kolor(image_path):
    try:
        image = kolor_adjuster.load(image_path)
        image = kolor_adjuster.auto_color_correct(image)
        processed_path = os.path.join(TEMP_DIR, f"processed_{os.path.basename(image_path)}")
        image.save(processed_path)
        return processed_path
    except Exception as e:
        app.logger.error(f"Kolor處理錯誤: {str(e)}")
        raise


def get_public_url(local_path):
    """將本地文件轉換為公開可訪問的URL"""
    # 這裡可以替換為你的CDN上傳邏輯
    # 簡化版: 假設有另一個端點提供文件訪問
    filename = os.path.basename(local_path)
    return f"https://{os.getenv('RENDER_SERVICE_URL')}/file/{filename}"


@app.route("/file/<filename>", methods=['GET'])
def serve_file(filename):
    """提供文件訪問的端點"""
    filepath = os.path.join(TEMP_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    return "File not found", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))