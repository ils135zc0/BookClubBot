import os
import random
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
import requests
from flask import Flask
from threading import Thread

# -----------------------
# .env 불러오기
# -----------------------
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ALADIN_API_KEY = os.getenv("ALADIN_API_KEY")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# -----------------------
# 장르 매핑
# -----------------------
genre_map = {
    "소설/시/희곡": 1,
    "장르소설": 112011,
    "역사": 74,
    "고전": 2105,
    "과학": 987,
    "사회": 798,
    "자기계발": 336,
    "청소년": 1137,
    "종교": 1237,
    "컴퓨터": 351,
    "만화": 2551,
    "경제": 170,
}

# -----------------------
# 알라딘 API 함수
# -----------------------
def fetch_books_by_genre(category_id, max_results=20, start_page=1):
    url = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"

    # 다양한 추천을 위해 QueryType을 무작위로 선택
    query_types = ["ItemNewAll", "ItemNewSpecial", "Bestseller", "ItemEditorChoice", "BlogBest"]
    selected_query_type = random.choice(query_types)

    params = {
        "ttbkey": ALADIN_API_KEY,
        "QueryType": selected_query_type,
        "CategoryId": category_id,
        "MaxResults": max_results,
        "start": start_page,
        "SearchTarget": "Book",
        "output": "js",
        "Version": "20131101",
    }

    response = requests.get(url, params=params)
    try:
        import json
        json_str = response.text.replace("var book = ", "").rstrip(";")
        data = json.loads(json_str)
        items = data.get("item", [])
        if not items:
            print(f"[경고] 장르 {category_id} 결과 없음. 응답: {data}")
        return items
    except Exception as e:
        print(f"[에러] JSON 파싱 실패: {e}")
        print(response.text[:200])
        return []

def fetch_books_by_keyword(keyword, max_results=10):
    url = "https://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
    params = {
        "ttbkey": ALADIN_API_KEY,
        "Query": keyword,
        "QueryType": "Keyword",
        "MaxResults": max_results,
        "start": 1,
        "SearchTarget": "Book",
        "output": "js",
        "Version": "20131101",
    }
    response = requests.get(url, params=params)
    try:
        import json
        json_str = response.text.replace("var book = ", "").rstrip(";")
        data = json.loads(json_str)
        items = data.get("item", [])
        if not items:
            print(f"[경고] 검색 '{keyword}' 결과 없음. 응답: {data}")
        return items
    except Exception as e:
        print(f"[에러] 검색 실패: {e}")
        print(response.text[:200])
        return []

# -----------------------
# Discord 봇 초기화
# -----------------------
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# -----------------------
# Embed 생성 함수
# -----------------------
def make_book_embed(book, selected_genre=None):
    embed = discord.Embed(
        title=book.get("title", "제목 없음"),
        description=book.get("description", "소개 없음")[:300],
        color=0x3498db,
    )
    embed.add_field(name="저자", value=book.get("author", "정보 없음"), inline=True)
    embed.add_field(name="출판사", value=book.get("publisher", "정보 없음"), inline=True)
    genre_display = book.get("categoryName", selected_genre if selected_genre else "정보 없음")
    embed.add_field(name="장르", value=genre_display, inline=False)
    if book.get("cover"):
        embed.set_thumbnail(url=book["cover"])
    return embed

# -----------------------
# 드롭다운 클래스
# -----------------------
class GenreSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=g, description=f"{g} 관련 도서를 추천합니다.")
            for g in genre_map.keys()
        ]
        super().__init__(placeholder="장르를 선택해 주세요.", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        genre = self.values[0]
        category_id = genre_map.get(genre)

        for _ in range(5):  # 최대 5번 재시도
            start_page = random.randint(1, 100)
            books = fetch_books_by_genre(category_id, start_page=start_page)
            if books:
                book = random.choice(books)
                embed = make_book_embed(book, selected_genre=genre)
                await interaction.followup.send(embed=embed)
                return

        await interaction.followup.send("❌ 해당 장르의 책을 찾지 못했습니다. 다시 시도해 주세요.", ephemeral=True)

class GenreSelectView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(GenreSelect())

# -----------------------
# /추천
# -----------------------
@tree.command(name="추천", description="장르의 책을 추천받습니다.")
async def recommend(interaction: discord.Interaction):
    view = GenreSelectView()
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send("📚 장르를 선택해 주세요!", view=view, ephemeral=True)

# -----------------------
# /랜덤
# -----------------------
@tree.command(name="랜덤", description="과연 어떤 책이 나올까요?")
async def random_book(interaction: discord.Interaction):
    await interaction.response.defer()
    for _ in range(5):
        category_id = random.choice(list(genre_map.values()))
        start_page = random.randint(1, 100)
        books = fetch_books_by_genre(category_id, start_page=start_page)
        if books:
            book = random.choice(books)
            embed = make_book_embed(book)
            await interaction.followup.send(embed=embed)
            return
    await interaction.followup.send("책을 불러올 수 없습니다. API Key 또는 카테고리를 확인하세요.", ephemeral=True)

# -----------------------
# /검색
# -----------------------
@tree.command(name="검색", description="키워드로 책을 검색합니다.")
@app_commands.describe(keyword="검색할 키워드")
async def search_book(interaction: discord.Interaction, keyword: str):
    await interaction.response.defer()
    books = fetch_books_by_keyword(keyword)
    if not books:
        await interaction.followup.send("해당 키워드로 책을 찾지 못했습니다.", ephemeral=True)
        return
    book = random.choice(books)
    embed = make_book_embed(book)
    await interaction.followup.send(embed=embed)

# -----------------------
# 하루 1회 자동 추천
# -----------------------
@tasks.loop(hours=24)
async def daily_recommendation():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("자동 추천 채널을 찾을 수 없습니다.")
        return
    for _ in range(5):
        category_id = random.choice(list(genre_map.values()))
        start_page = random.randint(1, 100)
        books = fetch_books_by_genre(category_id, start_page=start_page)
        if books:
            book = random.choice(books)
            embed = make_book_embed(book)
            await channel.send("오늘의 추천 도서입니다! 📚", embed=embed)
            return

# -----------------------
# 웹 서버 설정 (Replit용)
# -----------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

def start_web_server_thread():
    t = Thread(target=run_web_server)
    t.daemon = True
    t.start()

# -----------------------
# 봇 시작 시
# -----------------------
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ 로그인 완료: {bot.user}")
    print(f"✅ 슬래시 명령어 동기화 완료 ({len(tree.get_commands())}개)")
    if not daily_recommendation.is_running():
        daily_recommendation.start()

# -----------------------
# 봇 실행
# -----------------------
if __name__ == "__main__":
    start_web_server_thread()
    bot.run(DISCORD_TOKEN)