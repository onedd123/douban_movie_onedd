import requests
import json
import time
import os
from bs4 import BeautifulSoup
import re


class DoubanMovieToNotion:
    def __init__(self, douban_id, notion_token, database_id):
        self.douban_id = douban_id
        self.notion_token = notion_token
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def get_douban_movies(self):
        """获取豆瓣「看过」列表中的所有电影"""
        movies = []
        start = 0

        while True:
            url = f"https://movie.douban.com/people/{self.douban_id}/collect?start={start}&sort=time&rating=all&filter=all&mode=grid"

            try:
                response = requests.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                })
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.find_all('div', class_='item')

                if not items:
                    break

                for item in items:
                    movie_link = item.find('a', class_='nbg')
                    if not movie_link:
                        continue
                    movie_data = self.parse_movie_detail(movie_link['href'])

                    # 用户评分
                    user_rating_elem = item.find('span', class_=re.compile('rating'))
                    if user_rating_elem:
                        rating_class = user_rating_elem.get('class', [])
                        rating_str = next((c for c in rating_class if c.startswith('rating')), '')
                        if rating_str:
                            rating_num = rating_str.replace('rating', '').replace('-t', '')
                            movie_data['user_rating'] = int(rating_num) if rating_num.isdigit() else 0

                    # 观看日期
                    date_elem = item.find('span', class_='date')
                    if date_elem:
                        movie_data['watch_date'] = date_elem.text.strip()

                    # 短评
                    comment_elem = item.find('span', class_='comment')
                    if comment_elem:
                        movie_data['user_comment'] = comment_elem.text.strip()

                    movies.append(movie_data)
                    time.sleep(1)  # 礼貌抓取

                start += len(items)
                # 检查是否还有下一页
                next_page = soup.find('span', class_='next')
                if not next_page or not next_page.find('a'):
                    break

            except Exception as e:
                print(f"获取豆瓣电影数据时出错: {e}")
                break

        return movies

    def parse_movie_detail(self, url):
        """解析单个电影详情页"""
        try:
            response = requests.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            movie_data = {
                'title': '',
                'douban_rating': 0,
                'directors': [],
                'actors': [],
                'genres': [],
                'countries': [],
                'languages': [],
                'also_known_as': [],
                'durations': [],
                'imdb': '',
                'release_dates': [],
                'poster': '',
                'douban_url': url,
                'plot': '',
                'watch_status': '看过'
            }

            # 片名
            title_elem = soup.find('span', property='v:itemreviewed')
            if title_elem:
                movie_data['title'] = title_elem.text.strip()

            # 豆瓣评分
            rating_elem = soup.find('strong', property='v:average')
            if rating_elem and rating_elem.text:
                try:
                    movie_data['douban_rating'] = float(rating_elem.text)
                except ValueError:
                    movie_data['douban_rating'] = 0

            # 导演
            movie_data['directors'] = [elem.text for elem in soup.find_all('a', rel='v:directedBy')]

            # 主演（最多前5名）
            movie_data['actors'] = [elem.text for elem in soup.find_all('a', rel='v:starring')][:5]

            # 类型
            movie_data['genres'] = [elem.text for elem in soup.find_all('span', property='v:genre')]

            # 详细信息
            info_div = soup.find('div', id='info')
            if info_div:
                info_text = info_div.text
                patterns = {
                    'countries': r'制片国家/地区:\s*(.*)',
                    'languages': r'语言:\s*(.*)',
                    'also_known_as': r'又名:\s*(.*)',
                    'durations': r'(?:片长|单集片长):\s*(.*)',
                    'imdb': r'IMDb:\s*(tt\d+)'
                }
                for key, pat in patterns.items():
                    match = re.search(pat, info_text)
                    if match:
                        if key == 'imdb':
                            movie_data[key] = match.group(1)
                        else:
                            movie_data[key] = [x.strip() for x in match.group(1).split('/')]

            # 上映日期
            movie_data['release_dates'] = [elem.text for elem in soup.find_all('span', property='v:initialReleaseDate')]

            # 海报
            poster_elem = soup.find('img', rel='v:image')
            if poster_elem:
                movie_data['poster'] = poster_elem['src'].replace('s_ratio_poster', 'l_ratio_poster')

            # 剧情简介
            plot_elem = soup.find('span', property='v:summary')
            if plot_elem:
                movie_data['plot'] = plot_elem.text.strip()

            return movie_data

        except Exception as e:
            print(f"解析电影详情失败 {url}: {e}")
            return None

    def create_notion_page(self, movie):
        """向 Notion 数据库添加一条电影记录"""
        if not movie:
            return None

        properties = {
            "片名": {
                "title": [{"text": {"content": movie.get("title", "无标题")}}]
            },
            "豆瓣评分": {
                "number": movie.get("douban_rating", 0)
            },
            "导演": {
                "multi_select": [{"name": d} for d in movie.get("directors", [])[:5]]
            },
            "主演": {
                "multi_select": [{"name": a} for a in movie.get("actors", [])[:10]]
            },
            "类型": {
                "multi_select": [{"name": g} for g in movie.get("genres", [])]
            },
            "制片国家/地区": {
                "multi_select": [{"name": c} for c in movie.get("countries", [])]
            },
            "语言": {
                "multi_select": [{"name": l} for l in movie.get("languages", [])]
            },
            "又名": {
                "multi_select": [{"name": n} for n in movie.get("also_known_as", [])[:5]]
            },
            "片长/单集片长": {
                "multi_select": [{"name": d} for d in movie.get("durations", [])]
            },
            "IMDb": {
                "url": f"https://www.imdb.com/title/{movie['imdb']}" if movie.get('imdb') else None
            },
            "上映日期/首播": {
                "multi_select": [{"name": d} for d in movie.get("release_dates", [])[:3]]
            },
            "观看日期": {
                "date": {"start": movie.get("watch_date", "")} if movie.get("watch_date") else None
            },
            "我的评分": {
                "number": movie.get("user_rating", 0) / 2  # 转换为5分制
            },
            "我的短评": {
                "rich_text": [{"text": {"content": movie.get("user_comment", "")[:2000]}}]
            },
            "豆瓣链接": {
                "url": movie.get("douban_url", "")
            },
            "剧情简介": {
                "rich_text": [{"text": {"content": movie.get("plot", "")[:2000]}}]
            },
            "观影状态": {
                "select": {"name": movie.get("watch_status", "看过")}
            }
        }

        # 清理空值，避免 API 报错
        for key, value in properties.items():
            if isinstance(value, dict):
                if "multi_select" in value and not value["multi_select"]:
                    properties[key] = {"multi_select": []}
                elif "url" in value and not value["url"]:
                    properties[key] = {"url": None}
                elif "date" in value and not value["date"]:
                    properties[key] = {"date": None}

        cover = None
        if movie.get("poster"):
            cover = {"type": "external", "external": {"url": movie["poster"]}}

        data = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
            "cover": cover
        }

        try:
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers=self.headers,
                data=json.dumps(data)
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"创建页面失败: {e}")
            if 'response' in locals():
                print(f"Notion 返回: {response.text}")
            return None

    def sync(self):
        """执行一次完整的同步"""
        print("开始同步豆瓣电影数据到 Notion ...")
        movies = self.get_douban_movies()
        print(f"共获取到 {len(movies)} 部「看过」的电影")

        success = 0
        for i, movie in enumerate(movies):
            if movie is None:
                continue
            print(f"[{i+1}/{len(movies)}] 正在写入: {movie.get('title', '无标题')}")
            result = self.create_notion_page(movie)
            if result:
                success += 1
            time.sleep(1)

        print(f"同步完成，成功写入 {success} 部电影。")


if __name__ == "__main__":
    # 从环境变量读取配置
    DOUBAN_ID = os.environ.get("DOUBAN_ID")
    NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
    DATABASE_ID = os.environ.get("DATABASE_ID")

    if not all([DOUBAN_ID, NOTION_TOKEN, DATABASE_ID]):
        print("错误：请设置环境变量 DOUBAN_ID, NOTION_TOKEN, DATABASE_ID")
        exit(1)

    syncer = DoubanMovieToNotion(DOUBAN_ID, NOTION_TOKEN, DATABASE_ID)
    syncer.sync()