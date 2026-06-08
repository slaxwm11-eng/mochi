import os
import time
import yt_dlp
import subprocess

class AnimalLiveCamera:
    def __init__(self):
        # 统一输出目录，可以跟你的音频/图片缓存放在一起
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "animal_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.clip_seconds = 5
        
        self.animal_map = {
            "老鹰": "https://www.youtube.com/watch?v=B4-L2nfGcuE",
            "鱼鹰": "https://www.youtube.com/watch?v=VDXNDR1SjsQ",
            "热带鸟": "https://www.youtube.com/watch?v=WtoxxHADnGk",
            "大草原": "https://www.youtube.com/watch?v=8J9USywkGmw",
            "沙漠": "https://www.youtube.com/watch?v=ydYDqZQpim8",
            "红尾鵟": "https://www.youtube.com/watch?v=afsaYKQ3vac"
        }

    def _get_stream_url(self, url):
        """解析并返回 m3u8 纯净直播流"""
        ydl_opts = {"quiet": True, "live_from_start": False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            for f in info.get("formats", []):
                stream_url = f.get("url", "")
                if ".m3u8" in stream_url:
                    return stream_url
            return info["url"]

    def _record_and_convert(self, stream_url, output_gif_path):
        """录制 5 秒视频并直接转换为压缩版 GIF，全程在内存/临时管道处理最佳，但这里用临时 mp4 兜底最稳"""
        temp_mp4 = os.path.join(self.cache_dir, f"temp_{int(time.time())}.mp4")
        
        try:
            # 1. 录制原画 MP4
            rec_cmd = [
                "ffmpeg", "-y", "-rw_timeout", "15000000",
                "-i", stream_url, "-t", str(self.clip_seconds),
                "-c:v", "libx264", "-preset", "veryfast", temp_mp4
            ]
            subprocess.run(rec_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            # 2. 压制为丝滑小体积 GIF (QQ发送友好版)
            gif_cmd = [
                "ffmpeg", "-y", "-i", temp_mp4,
                "-vf", "fps=10,scale=480:-1:flags=lanczos", output_gif_path
            ]
            subprocess.run(gif_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            return os.path.exists(output_gif_path)
            
        finally:
            # 打扫战场：无论成功失败，删掉几百 MB 的临时 MP4 原片，防止硬盘撑爆
            if os.path.exists(temp_mp4):
                os.remove(temp_mp4)

    def get_animal_gif(self, animal_name):
        """
        供外部调用的主函数：
        传入动物名（如"大草原"），返回生成的 GIF 绝对路径。若失败或无此机位，返回 None。
        """
        if animal_name not in self.animal_map:
            return None
            
        target_url = self.animal_map[animal_name]
        
        # 加上时间戳，防止文件冲突
        final_gif_path = os.path.join(self.cache_dir, f"{animal_name}_{int(time.time())}.gif")
        
        try:
            stream_url = self._get_stream_url(target_url)
            success = self._record_and_convert(stream_url, final_gif_path)
            if success:
                return final_gif_path
            return None
        except Exception as e:
            print(f"❌ [AnimalCam] 抓取 {animal_name} 失败: {e}")
            return None
