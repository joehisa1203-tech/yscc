"""Write one day's article with the OpenAI API, or refuse to.

Why a writer at all: scripts/daily_blog.py rotates 24 hand-written tips, so the
same body text returns every 24 days. The LLM gives a different article daily.

Why it can refuse: this is a fan site, and the first rule of the project is that
no match result, attendance figure, ticket availability, player quote or
recruitment detail may be invented. A model cannot know those, so anything that
looks like one is treated as a defect and the article is thrown away — the
caller then falls back to the hand-written rotation. A plain blog that repeats
itself is a small problem; a fan site inventing a scoreline is not.
"""
from __future__ import annotations

import json
import os
import re

# 2026-11-23: Anthropicのアカウントはクレジット残高不足で呼び出せず、このVPSに
# 残高のあるOpenAIキーがあったため、呼び出し先をOpenAIに置き換えた。
# 事業者を戻す場合は、この呼び出し部分だけを差し替える（判定とフォールバックは
# 事業者に依存しない）。両方を並べて持たないのは、どちらが使われているか
# 分からなくなるのを避けるため。
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
CATEGORIES = ("観戦ガイド", "クラブを知る", "横浜の街")
# 人が選べるカテゴリー。トップページの絞り込みボタン（index.html の data-cat）と同じ並び。
# 「試合情報」はLLMには書かせない（試合の事実を知らないため）が、人が書いた記事には使う。
EDIT_CATEGORIES = ("観戦ガイド", "試合情報", "横浜の街", "クラブを知る")

SYSTEM = """あなたはY.S.C.C.横浜（日本フットボールリーグ=JFLに所属するサッカークラブ）の
非公式ファンメディア「BLUE COURT」の編集者です。ホームゲームの観客を増やすために、
読者が「次の週末にスタジアムへ行ってみよう」と思える短い記事を日本語で書きます。

絶対に守ること（破った記事は破棄されます）:
- 試合結果・スコア・順位・得点者を書かない。あなたは試合を見ていません。
- 観客数・来場者数を書かない。
- チケットの料金・残席・発売状況を書かない。「公式サイトで確認」と案内する。
- 選手・監督・クラブ関係者のコメントや発言を作らない。
- スクールやイベントの募集条件・日程・定員を作らない。
- クラブ公式を装わない。「独立したファンメディア」として書く。
- フットサル（F.LEAGUE）の話題を混ぜない。このメディアは11人制サッカー専門です。
- 具体的な数字（人数・金額・点数）を新しく作らない。

書き方:
- 読者は「サッカーをあまり見たことがない横浜の人」です。専門用語には短い説明を添える。
- 本文は3段落。各段落は100〜200文字。1〜2文で終わる短い段落は書かない。
- 煽らない。感嘆符を多用しない。断定できないことは断定しない。
- 観戦の楽しみ方、スタジアムでの過ごし方、サッカーの見どころ、横浜の街、
  クラブの成り立ちなど、調べなくても書ける普遍的な話題を選ぶ。
- 事実関係が必要なところは「公式サイトの最新情報を確認してください」と書く。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "title": {"type": "string", "description": "記事の見出し。20〜40文字程度。日付は含めない"},
        "summary": {"type": "string", "description": "一覧に出る要約。40〜80文字程度"},
        "body": {
            "type": "array",
            # minItems/maxItems はOpenAIのstrictモードが受け付けないため書かない。
            # 段落数は check() が3〜4本で判定する。
            "description": "本文の段落。必ず3段落。各段落100〜200文字（短い段落は不可）",
            "items": {"type": "string"},
        },
    },
    "required": ["category", "title", "summary", "body"],
    "additionalProperties": False,
}

# 検出したら記事を捨てる表現。右側はログに出す理由。
BANNED = [
    (r"\d+\s*[-−–―ー]\s*\d+", "スコアのような数字の並び"),
    (r"\d+\s*点", "得点の記述"),
    (r"\d+\s*人", "人数（観客数）の記述"),
    (r"\d+\s*円", "料金の記述"),
    (r"観客数|来場者数|入場者数", "観客数の記述"),
    (r"残席|完売|売り切れ|売切|即完", "チケット在庫の記述"),
    (r"勝利し|勝っ|敗れ|敗戦|引き分け|黒星|白星", "試合結果の記述"),
    (r"語った|話した|述べた|とコメント|の談話", "関係者コメントの捏造"),
    (r"募集中|募集し|定員|申込締切", "募集条件の記述"),
    (r"優勝|昇格が決|降格が決", "順位の確定情報"),
    (r"フットサル|F\.LEAGUE|ysccfutsal", "フットサルの混入"),
    (r"公式(サイト|メディア|アカウント)です", "公式を装う表現"),
]


def configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def status() -> str:
    """Why the writer is off, without printing any key material."""
    if not configured():
        return "OPENAI_API_KEY is not set"
    return f"configured (model {MODEL})"


def check(article: dict, recent_titles: list[str]) -> list[str]:
    """Return every reason this article must not be published. Empty = publishable."""
    problems: list[str] = []
    category = article.get("category")
    if category not in CATEGORIES:
        problems.append(f"カテゴリーが規定外: {category!r}")
    title = str(article.get("title", ""))
    summary = str(article.get("summary", ""))
    body = article.get("body") or []
    if not 10 <= len(title) <= 70:
        problems.append(f"タイトルの長さが範囲外: {len(title)}文字")
    if not 20 <= len(summary) <= 140:
        problems.append(f"要約の長さが範囲外: {len(summary)}文字")
    if not isinstance(body, list) or not 3 <= len(body) <= 4:
        problems.append(f"段落数が範囲外: {len(body) if isinstance(body, list) else type(body)}")
    else:
        for index, paragraph in enumerate(body, 1):
            if not isinstance(paragraph, str) or not 60 <= len(paragraph) <= 400:
                problems.append(f"{index}段落目の長さが範囲外")
    if title in recent_titles or any(title in t for t in recent_titles):
        problems.append("最近の記事と同じタイトル")
    problems.extend(banned_problems([title, summary, *[p for p in body if isinstance(p, str)]]))
    return problems


def banned_problems(parts: list[str]) -> list[str]:
    """BANNED に当たる表現をすべて返す。LLMの出力にも管理者の編集にも同じ判定を使う。"""
    text = "\n".join(parts)
    problems = []
    for pattern, reason in BANNED:
        found = re.search(pattern, text)
        if found:
            problems.append(f"{reason}（該当: {found.group(0)!r}）")
    return problems


def edit_problems(article: dict) -> list[str]:
    """管理画面で人が直した記事を公開してよいか。空なら公開できる。

    段落の長さや題材の重なりは LLM の品質管理なので、人の編集には課さない。
    **禁止表現は人が書いても公開しない。** 架空の試合結果・観客数を載せないという
    方針は、書き手がAIでも人でも同じだから（docs/admin.md）。
    """
    problems: list[str] = []
    if article.get("category") not in EDIT_CATEGORIES:
        problems.append(f"カテゴリーが規定外: {article.get('category')!r}")
    title = str(article.get("title", "")).strip()
    summary = str(article.get("summary", "")).strip()
    body = [p for p in (article.get("body") or []) if isinstance(p, str) and p.strip()]
    if not title:
        problems.append("タイトルが空です")
    if not summary:
        problems.append("要約が空です")
    if not body:
        problems.append("本文が空です")
    problems.extend(banned_problems([title, summary, *body]))
    return problems


# 題材を日付で回す。空のプロンプトだと「スタジアム周辺の街歩き」のような無難な
# 題材に寄り、3回続けてほぼ同じ記事になった（2026-11-23の実測）。
THEMES = (
    "初観戦の準備（持ち物・服装・到着時刻）",
    "スタジアムへの行き方と会場の見分け方",
    "サッカーの見どころ（ボールのない場所の動き）",
    "電子チケットの買い方と当日の入場",
    "家族や子どもと行く観戦",
    "一人で行く観戦の楽しみ方",
    "友人をサッカー観戦に誘うときの伝え方",
    "セットプレー（CK・FK）の見方",
    "守備から攻撃に変わる瞬間の面白さ",
    "ゴールキーパーの仕事を見る",
    "JFLというリーグの位置づけと地域クラブ",
    "Y.S.C.C.横浜というクラブの成り立ち",
    "横浜の街とスポーツ観戦のある週末",
    "観戦後に次の試合を探す習慣",
    "選手の名前を覚えていく楽しみ",
    "スタジアムでの撮影とまわりへの配慮",
)


def theme_for(date: str) -> str:
    from datetime import datetime
    ordinal = datetime.strptime(date, "%Y-%m-%d").date().toordinal()
    return THEMES[ordinal % len(THEMES)]


def build_prompt(date: str, recent_titles: list[str]) -> str:
    recent = "\n".join("- " + t for t in recent_titles[:20]) or "- （まだありません）"
    return f"""{date}（日本時間）に公開する記事を1本書いてください。

今日の題材: {theme_for(date)}
この題材に沿って書いてください。題材から外れた無難な内容にしないでください。

直近に公開した記事のタイトル（内容と切り口が重ならないようにしてください）:
{recent}

出力はスキーマどおりのJSONのみ。タイトルに日付は入れないでください。"""


def write_article(date: str, recent_titles: list[str], client=None) -> dict | None:
    """One OpenAI API call. Returns a checked article, or None (caller falls back)."""
    if not configured():
        print(f"[LLM] skipped: {status()}")
        return None
    if client is None:
        import openai  # imported here so the container runs without a key
        client = openai.OpenAI()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": build_prompt(date, recent_titles)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "blue_court_article", "strict": True, "schema": SCHEMA},
            },
        )
    except Exception as error:  # an API outage must not stop the blog
        print(f"[LLM] call failed, falling back to the written rotation: {error}")
        return None
    choice = response.choices[0]
    if choice.finish_reason != "stop":
        # length なら本文が途中で切れている。refusal なら拒否された。
        print(f"[LLM] unusable finish_reason={choice.finish_reason!r}")
        return None
    try:
        article = json.loads(choice.message.content)
    except (TypeError, ValueError) as error:
        print(f"[LLM] could not read the response: {error}")
        return None
    problems = check(article, recent_titles)
    if problems:
        for problem in problems:
            print(f"[LLM] rejected: {problem}")
        return None
    print(f"[LLM] wrote: {article['title']}")
    return article
