# GeminiAI_Discord-bot

# 使い方(起動編)

・GeminiのAPIキー取得
1. 次のURLにアクセスhttps://console.cloud.google.com/apis/credentials
2. 画面上部の「認証情報を作成」をクリック
3. APIキーを選択
4. 作成されたAPIキーをコピーする（このAPIキーは外部に流出させないこと）
5. .envにAPIキーを書き込む
6. これを三回繰り返す


・Discordbotの作成・APIキーの取得
1. New Applicationをクリック、NAMEを入力して、チェックボックスにチェックして、作成
2. Installation→Install LinkをNoneに変更。画面下の「Save Changes」を押す。
3. Bot→MESSAGE CONTENT INTENTをオンに変更。画面下の「Save Changes」を押す。
4. Bot→PUBLIC Botをオフに変更。画面下の「Save Changes」を押す。
5. Bot→Reset Tokenでトークンをリセット、表示されたトークンをコピーしておくこと（このトークンは外部に流出させないこと。リセットすると前のトークンは使えなくなる）
6. .envにAPIキーを書き込む
7. (サーバへの招待。後回しでも良い)OAuth2→OAuth2 URL Generatorからbotを選択、さらに下へスクロールして、View Channels, Send Message, Attach File, Mention Everyoneの4項目を選択、一番下のGENERATED URLのリンクをコピー。このリンクをブラウザに入力した先でbotをサーバに招待する。
8. これを三回繰り返す


1. GitHubのソースコードをDLする $ git clone git@github.com:Rosy6/GeminiAI_Discord-bot.git 
2. .envファイルを作成し、先ほど取得したGeminiのAPIキーとDiscordのトークンを書き込む。

$  ls ./
bot_main.py		Dockerfile		shared
docker-compose.yml	requirements.txt
$ vim ./.env
.env
GEMINI_TOKEN1="YOUR-GEMINI-API-KEY1"
GEMINI_TOKEN2="YOUR-GEMINI-API-KEY2"
GEMINI_TOKEN3="YOUR-GEMINI-API-KEY3"
DISCORD_TOKEN1="YOUR-DISCORDBOT-TOKEN1"
DISCORD_TOKEN2="YOUR-DISCORDBOT-TOKEN2"
DISCORD_TOKEN3="YOUR-DISCORDBOT-TOKEN3"

2. Docker環境を整備する。（参考：https://qiita.com/haveAbook/items/0d0ae20a19214f65e7cd ）

3. Dockerを起動する
$ ls ./
bot_main.py		Dockerfile		shared
docker-compose.yml	requirements.txt
$ docker compose up --build

# コマンドリスト(メンションの後にこれらのコマンドを打ち込む)
!check,ボットがこのチャンネルを監視しているか確認。
!list_channel,設定されている応答チャンネルの一覧を表示。
!send_config,チャンネルの設定ファイルを送信。
!reset_config,チャンネルの設定ファイルをリセット。
!send_history,現在のチャット履歴をJSON形式で送信。
!reset_chat,現在のチャット履歴をリセットし、設定も削除。
!save_chat,現在のチャット履歴を指定した場所に保存。
!list_chat,保存されたチャット履歴一覧を表示。
!load_chat {チャット名},指定されたチャット名からチャット履歴と設定を復元。
!send_buffered,現在のメッセージバッファ(AIへ未送信の非メンションメッセージ)の内容を送信。
!reset_buffered：現在のメッセージバッファ(AIへ未送信の非メンションメッセージ)の内容を削除。
!send_last,最後に記憶しているメッセージを送信。
!send_lastdata：最後の会話でのAIのメタデータを送信