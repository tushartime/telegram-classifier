Telegram Course Classifer — MVP

What this does
- Indexes a Telegram channel's video messages (metadata only)
- Infers a folder-like structure (course → sections → lectures)
- Creates real Windows folders with .url shortcuts that open the original Telegram post

Quickstart
1. Copy `.env.example` to `.env` and fill TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSION_NAME.
2. Install dependencies:
   pip install -r requirements.txt
3. Run importer:
   python src/run_import.py --channel <channel_username_or_id> --limit 500 --out ./output

Result
- The `./output` folder will contain a course folder with section subfolders and `.url` files for each lecture.

Notes
- This MVP does not download video files. It only creates a browsable structure and shortcuts that open the original Telegram message.
- For private channels you must run with a Telegram user account that has access.

Electron UI
- Install node dev dependency: npm install
- Start the overlay: npm run start
The Electron renderer provides a small GUI to input a channel, run the importer, and browse the generated tree. Clicking a lecture opens the Telegram link in your browser/Telegram app.

Auto-classification with LLM
- The app can use an LLM (e.g. Gemini over HTTP) to group videos into topics. You can either:
  - Let the LLM invent topic names on its own (e.g. "Sales Training", "Video Editing", "Chatbot Automation"), or
  - Provide your own category list (e.g. "Verbal, Quant, Aptitude, Reasoning") and force everything into those buckets.

Configuration (HTTP / Gemini-style endpoint)
- To supply a Gemini/LLM HTTP endpoint and API key, set:
  - LLM_BACKEND=gemini
  - GEMINI_API_URL=<your-llm-endpoint>
  - GEMINI_API_KEY=<your-api-key>
- The code will POST a JSON payload `{ "prompt": "...", "max_output_tokens": 64, "temperature": 0.0 }` to `GEMINI_API_URL` with `Authorization: Bearer GEMINI_API_KEY` and expect the model's text response. The classifier takes the first non-empty line as the category name (or created topic) and uses it as the folder/category name.
- This mode does not require any Google Cloud SDK or Vertex configuration; you only need the HTTP URL and key provided by your LLM service.

Examples:
  set LLM_BACKEND=gemini
  set GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta2/models/text-bison:predict
  set GEMINI_API_KEY=ya29.your_api_key_here

Notes:
- The HTTP endpoint and exact payload format may vary by provider. If your provider expects a different JSON schema, set LLM_BACKEND=http and provide LLM_API_URL / LLM_API_KEY env vars instead.
- Calls may incur cost; consider caching results.
If no LLM is configured, items fall into a generic "Uncategorized" bucket.

