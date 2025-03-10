import time
import logging
import xml.etree.ElementTree as ET
import re
import aiohttp
import asyncio


logger = logging.getLogger(__name__)

class AppleMusicAPI:
    def __init__(self):
        self.authorization = ('')
        self.token = ('')
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Authorization": self.authorization,
            "music-user-token": self.token,
            "Origin": "https://music.apple.com",
            "Referer": "https://music.apple.com/",
        }
        self.session = None
        self.ttml_lyric_cache = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def ensure_session(self):
        """确保session已创建"""
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
            # 测试会话是否可用
            elif self.session.closed:
                logger.warning("会话已关闭，重新创建")
                self.session = aiohttp.ClientSession()
        except Exception as e:
            logger.error(f"创建会话时出错: {e}")
            # 强制重建会话
            try:
                if self.session:
                    await self.session.close()
            except:
                pass
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        """关闭session"""
        try:
            if self.session and not self.session.closed:
                await self.session.close()
        except Exception as e:
            logger.error(f"关闭会话时出错: {e}")
        finally:
            self.session = None

    def data_parser_song(self, data: dict) -> dict:
        """
        解析音乐数据(从搜索，需要额外请求歌词)
        :param data: 原始响应数据
        :param lyrics: 歌词数据
        :return: 整理后的音乐数据
        """
        try:
            attributes = data.get('attributes', {})
            # 嵌套字典取值
            relationships = data.get('relationships', {})
            
            # 获取artists_id
            artists_data = relationships.get('artists', {}).get('data', [])
            artists_id = []
            for ar in artists_data:
                ar_id = ar.get('id')
                if ar_id:
                    artists_id.append(ar_id)
            
            # albums_id
            albums_data = relationships.get('albums', {}).get('data', [])
            albums_id = []
            for al in albums_data:
                al_id = al.get('id')
                if al_id:
                    albums_id.append(al_id)
            
            # 封面信息
            artwork = attributes.get('artwork', {})
            cover_format = artwork.get('url', '')
            width = artwork.get('width', 2000)
            height = artwork.get('height', 2000)
            cover_url = ''
            if cover_format:
                try:
                    cover_url = cover_format.format(w=width, h=height, f='jpg')
                except KeyError as e:
                    logger.error(f"封面URL格式化错误: {e}, 原格式: {cover_format}")
                except Exception as e:
                    logger.error(f"封面URL处理错误: {e}")
            
            # 歌词信息
            syllable_lyrics = relationships.get('syllable-lyrics', {})
            lyric_path = syllable_lyrics.get('href', '')
            syllable_lyrics_data = syllable_lyrics.get('data', [])
            
            lyrics_ttml_data = ''
            if syllable_lyrics_data and len(syllable_lyrics_data) > 0:
                lyrics_ttml_data = syllable_lyrics_data[0].get('attributes', {}).get('ttml', '')
            
            lrc_ttml = lyrics_ttml_data or self.ttml_lyric_cache.get(lyric_path, '')
            lrc = self.ttml_to_lrc(lrc_ttml)
            
            return {
                "title": attributes.get('name', ''),                        # 歌曲名
                "object_type": "song",                                      # 对象类型
                "object_id": data.get('id', ''),                            # 歌曲ID
                "album": attributes.get('albumName', ''),                   # 专辑名
                "album_id": albums_id,                                      # 专辑ID（列表）
                "artists": attributes.get('artistName', ''),                # 艺术家名
                "artists_id": artists_id,                                   # 艺术家ID（列表）
                "composerName": attributes.get('composerName', ''),         # 作曲家名
                "cover_format": cover_format,                               # 封面格式
                "cover": cover_url,                                         # 封面URL
                "duration": attributes.get('durationInMillis', 0) / 1000,   # 歌曲时长
                "audioLocale": attributes.get('audioLocale', ''),           # 音频语言
                "isrc": attributes.get('isrc', ''),                         # ISRC
                "discNumber": attributes.get('discNumber', 0),              # 碟片号
                "trackNumber": attributes.get('trackNumber', 0),            # 曲目号
                "genreNames": attributes.get('genreNames', []),             # 流派
                "releaseDate": attributes.get('releaseDate', ''),           # 发行日期
                "lyric_path": lyric_path,                                   # 歌词URL
                "lrc_ttml": lrc_ttml,                                       # 歌词TTML
                "lrc": lrc,                                                 # 歌词LRC
                "update_time": time.time()                                  # 更新时间
            }
        except KeyError as e:
            # 记录详细错误信息但不包含过长的数据内容
            logger.error(f"解析Apple Music歌曲数据时出现KeyError: {e}, 数据ID: {data.get('id', 'unknown')}")
            return {}
        except Exception as e:
            logger.error(f"解析Apple Music歌曲数据时出现异常: {e}, 数据ID: {data.get('id', 'unknown')}")
            return {}
        
    @staticmethod
    def data_parser_album(data: dict) -> dict:
        """
        解析专辑数据
        :param data: 原始响应数据
        :return: 整理后的专辑数据
        """
        try:
            attributes = data.get('attributes', {})
            artwork = attributes.get('artwork', {})
            cover_format = artwork.get('url', '')
            width = artwork.get('width', 2000)
            height = artwork.get('height', 2000)
            cover_url = ''
            if cover_format:
                try:
                    cover_url = cover_format.format(w=width, h=height, f='jpg')
                except KeyError as e:
                    logger.error(f"专辑封面URL格式化错误: {e}, 原格式: {cover_format}")
                except Exception as e:
                    logger.error(f"专辑封面URL处理错误: {e}")

            # 获取artists_id
            relationships = data.get('relationships', {})
            artists_data = relationships.get('artists', {}).get('data', [])
            artists_id = []
            for ar in artists_data:
                ar_id = ar.get('id')
                if ar_id:
                    artists_id.append(ar_id)

            return {
                "album": attributes.get('name', ''),
                "object_type": "album",
                "object_id": data.get('id', ''),
                "artists": attributes.get('artistName', ''),
                "artists_id": artists_id,
                "cover_format": cover_format,
                "cover": cover_url,
                "trackCount": attributes.get('trackCount', 0),
                "releaseDate": attributes.get('releaseDate', ''),
                "genreNames": attributes.get('genreNames', []),
                "update_time": time.time()
            }
        except KeyError as e:
            logger.error(f"解析Apple Music专辑数据时出现KeyError: {e}, 数据ID: {data.get('id', 'unknown')}")
            return {}
        except Exception as e:
            logger.error(f"解析Apple Music专辑数据时出现异常: {e}, 数据ID: {data.get('id', 'unknown')}")
            return {}

    @staticmethod
    def data_parser_artist(data: dict) -> dict:
        """
        解析艺术家数据
        :param data: 原始响应数据
        :return: 整理后的艺术家数据
        """
        try:
            attributes = data.get('attributes', {})
            artwork = attributes.get('artwork', {})
            cover_format = artwork.get('url', '')
            width = artwork.get('width', 2000)
            height = artwork.get('height', 2000)
            cover_url = ''
            if cover_format:
                try:
                    cover_url = cover_format.format(w=width, h=height, f='jpg')
                except KeyError as e:
                    logger.error(f"艺术家封面URL格式化错误: {e}, 原格式: {cover_format}")
                except Exception as e:
                    logger.error(f"艺术家封面URL处理错误: {e}")

            return {
                "name": attributes.get('name', ''),
                "object_type": "artist",
                "object_id": data.get('id', ''),
                "cover_format": cover_format,
                "cover": cover_url,
                "genreNames": attributes.get('genreNames', []),
                "update_time": time.time()
            }
        except KeyError as e:
            logger.error(f"解析Apple Music艺术家数据时出现KeyError: {e}, 数据ID: {data.get('id', 'unknown')}")
            return {}
        except Exception as e:
            logger.error(f"解析Apple Music艺术家数据时出现异常: {e}, 数据ID: {data.get('id', 'unknown')}")
            return {}

    @staticmethod
    def to_standard_time(time: str) -> str:
        """
        将时间转换为标准格式
        47.243 -> 00:47.243
        04:24.638 -> 04:24.638
        1:2:3.4 -> 62:03.400
        """
        # 只保留数字、小数点、冒号
        _time = re.sub(r'[^0-9.:]', '', time)
        times = _time.split(':')
        
        def parse_milliseconds(ms_str: str) -> int:
            """处理毫秒部分，根据位数调整值"""
            if not ms_str:
                return 0
            # 根据毫秒的位数进行处理
            if len(ms_str) == 1:
                return int(ms_str) * 100    # 一位数字，如 .4 -> 400
            elif len(ms_str) == 2:
                return int(ms_str) * 10     # 两位数字，如 .45 -> 450
            else:
                return int(ms_str[:3])      # 取前三位，如 .456789 -> 456

        if len(times) == 1:
            hours = 0
            minutes = 0
            # 将时间字符串分割成整数和小数部分
            seconds_parts = times[0].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = parse_milliseconds(seconds_parts[1]) if len(seconds_parts) > 1 else 0
        elif len(times) == 2:
            hours = 0
            minutes = int(times[0])
            seconds_parts = times[1].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = parse_milliseconds(seconds_parts[1]) if len(seconds_parts) > 1 else 0
        elif len(times) == 3:
            hours = int(times[0])
            minutes = int(times[1])
            seconds_parts = times[2].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = parse_milliseconds(seconds_parts[1]) if len(seconds_parts) > 1 else 0
        
        # 处理进位
        minutes += hours * 60
        if seconds >= 60:
            minutes += seconds // 60
            seconds = seconds % 60
            
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    
    def ttml_to_lrc(self, ttml: str) -> str:
        """
        解析TTML格式歌词为LRC格式歌词或纯文本歌词
        Args:
            ttml: TTML格式歌词
        Returns:
            str: LRC格式歌词或纯文本歌词
        """
        if not ttml:
            return ''
        
        # 定义TTML命名空间
        namespaces = {
            'tt': 'http://www.w3.org/ns/ttml',
            'itunes': 'http://music.apple.com/lyric-ttml-internal'
        }
        
        root = ET.fromstring(ttml)
        lrc_body: list = []
        
        # 使用命名空间查找body标签
        body = root.find('.//tt:body', namespaces)
        if body is None:
            body = root.find('body')
            if body is None:
                logger.error("无法在TTML中找到body标签")
                return ''
            
        # 检查是否为无时间标记的歌词
        if 'itunes:timing="None"' in ttml:
            # 获取所有div标签
            divs = body.findall('.//tt:div', namespaces) or body.findall('div')
            text_lines = []
            
            for div in divs:
                # 查找所有p标签
                lines = div.findall('.//tt:p', namespaces) or div.findall('p')
                for line in lines:
                    # 获取<span>标签
                    spans = line.findall('.//tt:span', namespaces) or line.findall('span')
                    if spans:
                        text = ''.join(line.itertext()).strip()
                    else:
                        text = line.text.strip() if line.text else ''
                    if text:
                        text_lines.append(text)
                    
            return "[!text]" + '\n'.join(text_lines)
        
        # 获取所有div标签
        divs = body.findall('.//tt:div', namespaces) or body.findall('div')
        
        for div in divs:
            div_itunes_songPart: str = div.get('{http://music.apple.com/lyric-ttml-internal}songPart') or div.get('itunes:songPart')
            # 查找所有p标签
            lines = div.findall('.//tt:p', namespaces) or div.findall('p')
            if div_itunes_songPart:
                lrc_body.append({
                    'type': 'mark',
                    'part': div_itunes_songPart
                })
            for line in lines:
                line_begin: str = line.get('begin')
                line_end: str = line.get('end')
                # 获取<span>标签
                spans = line.findall('.//tt:span', namespaces) or line.findall('span')
                line_text: str = ''
                if spans:
                    full_text = ''.join(line.itertext()).strip()
                    line_text = full_text
                else:
                    line_text = line.text.strip() if line.text else ''
                lrc_body.append({
                    'type': 'line',
                    'begin': line_begin,
                    'end': line_end,
                    'text': line_text
                })

        lrc_text = ''
        for item in lrc_body:
            if item.get('type') == 'mark':
                lrc_text += f"[{item.get('part')}]\n"
            elif item.get('type') == 'line':
                lrc_text += f"[{self.to_standard_time(item.get('begin'))}]{item.get('text')}\n"
        return lrc_text
    
    async def get_lyric(self, path: str) -> str:
        """获取歌曲的TTML格式歌词数据
        Args:
            path: 歌曲路径
        Returns:
            str: 歌词数据，获取失败返回空字符串
        """
        if not path:
            return ''
        
        await self.ensure_session()
        url = f"https://amp-api.music.apple.com{path}"
        params = {
            'l': 'zh-Hans-CN'
        }
        try:
            async with self.session.get(url=url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["data"][0]["attributes"]["ttml"]
                else:
                    logger.error(f"获取TTML歌词失败: {response.status}")
                    return ''
        except Exception as e:
            logger.error(f"获取TTML歌词时发生错误: {str(e)}")
            return ''

    async def search_songs(self, name: str, artist: str, album: str) -> list:
        """
        搜索歌曲
        """
        await self.ensure_session()
        url = "https://amp-api-edge.music.apple.com/v1/catalog/us/search"
        params = {
            'art[music-videos:url]': 'c',
            'art[url]': 'f',
            'extend': 'artistUrl',
            'relate[albums]': 'artistName,artistUrl,artwork,contentRating,editorialArtwork,editorialNotes,name,playParams,releaseDate,url,trackCount',
            'fields[artists]': 'url,name,artwork',
            'format[resources]': 'map',
            'include[albums]': 'artists',
            'include[music-videos]': 'artists',
            'include[songs]': 'artists,lyrics,syllable-lyrics',
            'include[stations]': 'radio-show',
            'l': 'zh-Hans-CN',
            'limit': '21',
            'omit[resource]': 'autos',
            'platform': 'web',
            'relate[albums]': 'artists',
            'relate[songs]': 'albums',
            'term': f"{name} {artist} {album}" if album else f"{name} {artist}",
            'types': 'activities,albums,apple-curators,artists,curators,editorial-items,music-movies,music-videos,playlists,record-labels,songs,stations,tv-episodes,uploaded-videos',
            'with': 'lyricHighlights,lyrics,serverBubbles'
        }
        
        async with self.session.get(url=url, headers=self.headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                results = []
                if 'resources' in data and 'songs' in data['resources']:
                    songs = data['resources']['songs']
                    lyrics = data['resources']['lyrics']
                    # 创建一个缓存，用于存储已获取的歌词
                    self.ttml_lyric_cache = {}
                    
                    # 预先获取所有歌词
                    for song_id, song_data in songs.items():
                        if song_data['type'] == 'songs':
                            syllable_lyrics = song_data.get('relationships', {}).get('syllable-lyrics', {})
                            lyric_path = syllable_lyrics.get('href', '')
                            if lyric_path and not syllable_lyrics.get('data'):
                                ttml = await self.get_lyric(lyric_path)
                                self.ttml_lyric_cache[lyric_path] = ttml
                    
                    for song_id, song_data in songs.items():
                        if song_data['type'] == 'songs':
                            source_data: dict = self.data_parser_song(song_data)
                            results.append(source_data)
                return results
            return []
        
    async def get_album(self, album_id: str, get_all: bool = False) -> dict:
        """
        获取专辑数据
        """
        await self.ensure_session()
        url = f"https://amp-api.music.apple.com/v1/catalog/us/albums/{album_id}"
        params = {
            "l": "zh-Hans-CN",
            "relate[albums]": "artists",
        }
        
        async with self.session.get(url=url, headers=self.headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if len(data.get('data', [])) > 0:
                    if get_all:
                        return data.get('data', [])[0]
                    else:
                        return self.data_parser_album(data.get('data', [])[0])
                else:
                    logger.error(f"获取专辑数据失败: 响应中无有效数据, ID: {album_id}")
                    return {}
            else:
                logger.error(f"获取专辑数据失败: HTTP状态码 {response.status}, ID: {album_id}")
                return {}
        
    async def get_artist(self, artist_id: str, get_all: bool = False) -> dict:
        """
        获取艺术家数据
        """
        await self.ensure_session()
        url = f"https://amp-api.music.apple.com/v1/catalog/us/artists/{artist_id}"
        params = {
            "l": "zh-Hans-CN",
        }
        
        async with self.session.get(url=url, headers=self.headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if len(data.get('data', [])) > 0:
                    if get_all:
                        return data.get('data', [])[0]
                    else:
                        return self.data_parser_artist(data.get('data', [])[0])
                else:
                    logger.error(f"获取艺术家数据失败: 响应中无有效数据, ID: {artist_id}")
                    return {}
            else:
                logger.error(f"获取艺术家数据失败: HTTP状态码 {response.status}, ID: {artist_id}")
                return {}
        
    async def get_song(self, song_id: str) -> dict:
        """
        获取歌曲数据
        """
        await self.ensure_session()
        url = f"https://amp-api.music.apple.com/v1/catalog/us/songs/{song_id}"
        params = {
            "l": "zh-Hans-CN",
            "fields[artists]": "url,name,artwork",
            "fields[resources]": "map",
            "platform": "web",
            "include": "albums,artists,credits,lyrics,music-videos,syllable-lyrics",
            "relate[songs]": "artists,lyrics,syllable-lyrics",
        }
        
        async with self.session.get(url=url, headers=self.headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if len(data.get('data', [])) > 0:
                    # 获取歌词
                    song_data = data.get('data', [])[0]
                    syllable_lyrics = song_data.get('relationships', {}).get('syllable-lyrics', {})
                    lyric_path = syllable_lyrics.get('href', '')
                    if lyric_path and not syllable_lyrics.get('data'):
                        # 创建一个临时缓存
                        self.ttml_lyric_cache = {}
                        ttml = await self.get_lyric(lyric_path)
                        self.ttml_lyric_cache[lyric_path] = ttml
                    else:
                        self.ttml_lyric_cache = {}
                        
                    return self.data_parser_song(song_data)
                else:
                    logger.error(f"获取歌曲数据失败: 响应中无有效数据, ID: {song_id}")
                    return {}
            else:
                logger.error(f"获取歌曲数据失败: HTTP状态码 {response.status}, ID: {song_id}")
                return {}
            
    async def search_api(self, keyword: str):
        """
        搜索API
        """
        await self.ensure_session()
        url = "https://amp-api-edge.music.apple.com/v1/catalog/us/search"
        search_params = {
            'art[music-videos:url]': 'c',
            'art[url]': 'f',
            'extend': 'artistUrl',
            'relate[albums]': 'artists',
            'fields[artists]': 'url,name,artwork',
            'format[resources]': 'map',
            'include[albums]': 'artists',
            'include[music-videos]': 'artists',
            'include[songs]': 'artists',
            'include[stations]': 'radio-show',
            'l': 'zh-Hans-CN',
            'limit': '21',
            'omit[resource]': 'autos',
            'platform': 'web',
            'relate[albums]': 'artists',
            'relate[songs]': 'albums',
            'term': keyword,
            'types': 'activities,albums,apple-curators,artists,curators,editorial-items,music-movies,music-videos,playlists,record-labels,songs,stations,tv-episodes,uploaded-videos',
            'with': 'lyricHighlights,lyrics,serverBubbles'
        }
        async with self.session.get(url=url, headers=self.headers, params=search_params) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                logger.error(f"搜索API失败: HTTP状态码 {response.status}")
                return {}
        
    async def search(self, name: str='', artist: str='', album: str=''):
        """
        搜索歌曲
        """
        params = [x for x in (name, artist, album) if x]
        if len(params) == 0:
            return []
        params = params[:2]

        await self.ensure_session()
            
        try:
            data = await self.search_api(" ".join(params))
            results: list[dict] = []
            
            # 安全地获取顶部结果
            results_data = data.get('results', {})
            if not results_data:
                logger.warning("Apple Music搜索返回的结果为空")
                return []
                
            top_data = results_data.get('top', {})
            if not top_data:
                logger.warning("Apple Music搜索返回的top字段为空")
                return []
                
            top = top_data.get("data", [])
            if not top:
                logger.warning("Apple Music搜索返回的data字段为空")
                return []
            
            type_handlers = {
                "songs": (self.get_song, results.append),
                "albums": (self.get_album, results.append),
                "artists": (self.get_artist, results.append)
            }
            
            # 分别异步获取所有条目的详细信息
            tasks = []
            for item in top:
                item_type = item.get('type')
                item_id = item.get('id')
                
                if not item_type or not item_id:
                    logger.warning(f"忽略无效的搜索结果项: {item}")
                    continue
                    
                handler = type_handlers.get(item_type)
                if handler:
                    get_method, _ = handler
                    tasks.append(get_method(item_id))
                else:
                    logger.debug(f"未处理的项目类型: {item_type}")
            
            if not tasks:
                logger.warning("没有找到可处理的搜索结果")
                return []
            
            # 等待所有任务完成
            results_data = await asyncio.gather(*tasks)
            
            # 筛选掉空结果并存入数据库
            for result in results_data:
                if result:  # 非空
                    try:
                        results.append(result)
                    except Exception as e:
                        logger.error(f"处理或保存Apple Music搜索结果时出错: {e}, 数据ID: {result.get('object_id', 'unknown')}")
                        
            return results
        except KeyError as e:
            # 提供精确的错误信息，但不记录大量JSON数据
            key_path = str(e).strip("'")
            logger.error(f"处理Apple Music搜索结果时出现KeyError: 缺少键 '{key_path}'")
            return []
        except Exception as e:
            logger.error(f"处理Apple Music搜索结果时出现异常: {e}")
            return []
        
    async def param_playlist_api(self, playlist_id: str):
        """
        获取播放列表数据
        """
        await self.ensure_session()
        url = f"https://amp-api.music.apple.com/v1/catalog/us/playlists/{playlist_id}?art%5Burl%5D=f&extend=editorialArtwork%2CeditorialVideo%2Coffers%2CseoDescription%2CseoTitle%2CtrackCount&fields%5Balbums%5D=name%2Cartwork%2CplayParams%2Curl&fields%5Bapple-curators%5D=name%2Curl&fields%5Bartists%5D=name%2Cartwork%2Curl&fields%5Bcurators%5D=name%2Curl&fields%5Bsongs%5D=name%2CartistName%2CcuratorName%2CcomposerName%2Cartwork%2CplayParams%2CcontentRating%2CalbumName%2Curl%2CdurationInMillis%2CaudioTraits%2CextendedAssetUrls&format%5Bresources%5D=map&include=tracks%2Ccurator&include%5Bmusic-videos%5D=artists&include%5Bsongs%5D=artists&l=zh-Hans-CN&limit%5Btracks%5D=300&limit%5Bview.featured-artists%5D=15&limit%5Bview.more-by-curator%5D=15&omit%5Bresource%5D=autos&platform=web&views=featured-artists%2Cmore-by-curator"
        async with self.session.get(url=url, headers=self.headers) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                logger.error(f"获取播放列表数据失败: HTTP状态码 {response.status}")
                return {}
    
        
                        
if __name__ == "__main__":
    async def main():
        logging.basicConfig(level=logging.DEBUG)
        api = AppleMusicAPI()
        try:
            result = await api.get_artist("300117743")
            print(result)
        finally:
            await api.close()
            
    asyncio.run(main())
