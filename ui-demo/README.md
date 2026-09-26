# VinBank chatbot demo

Giao diện demo local cho **Blue Team**. Server dùng Blue pipeline có sẵn:

```text
Rate limiter → Input guardrail → Blue LLM → Output guardrail
```

Chạy từ gốc repo sau khi đã cài dependencies và cấu hình `OPENROUTER_API_KEY` trong `.env`:

```bash
source .venv/bin/activate
python ui-demo/app.py
```

Mở <http://127.0.0.1:8080>. Dừng server bằng `Ctrl+C`.

Server chỉ bind vào localhost. Browser không nhận API key; key chỉ được đọc ở backend local qua cấu hình có sẵn của repo.

Nếu OpenRouter không phản hồi trong khoảng 15 giây (key, quota hoặc mạng), giao diện
sẽ trả một câu hướng dẫn **"Chế độ demo local"**. Đây là fallback được gắn nhãn rõ
ràng, không phải phản hồi của LLM live. Các input bị guardrail chặn vẫn hiển thị là
blocked trước khi fallback có thể được dùng.
