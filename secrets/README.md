# secrets/

`secrets/` の中身は `.gitignore` で除外しています（この README だけが例外）。

- `google-service-account.json` … Google Cloud で作成したサービスアカウント鍵。
  利用者本人がここへ置いてください。中身をチャットや issue に貼らないこと。

コンテナからは読み取り専用（`:ro`）で `/secrets/` としてマウントされます。
