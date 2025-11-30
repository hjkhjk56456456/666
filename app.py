from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from pytube import YouTube
from pytube.exceptions import VideoUnavailable, AgeRestrictedError, PytubeError
import os
import re
import tempfile
from dotenv import load_dotenv
import logging
from datetime import datetime
import io

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 全局配置
MAX_VIDEO_DURATION = 3600  # 最大允许下载的视频时长(秒)，1小时
ALLOWED_DOMAINS = {'youtube.com', 'youtu.be'}

def is_valid_youtube_url(url):
    """验证YouTube URL是否有效"""
    try:
        # 检查域名
        domain = re.search(r'https?://(www\.)?([^/]+)', url).group(2)
        if domain not in ALLOWED_DOMAINS and not any(domain.endswith(d) for d in ALLOWED_DOMAINS):
            return False
            
        # 检查视频ID格式
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
        return bool(video_id_match)
    except:
        return False

def get_video_info(video_id):
    """获取视频基本信息和可用流"""
    try:
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        
        # 检查视频时长
        if yt.length > MAX_VIDEO_DURATION:
            raise ValueError(f"视频时长超过限制({MAX_VIDEO_DURATION//60}分钟)")
            
        # 获取可用的视频流(仅包含mp4格式和视频+音频的流)
        streams = yt.streams.filter(
            file_extension='mp4',
            progressive=True  # 包含音频和视频的流
        ).order_by('resolution').desc()
        
        # 格式化流信息
        formatted_streams = []
        for stream in streams:
            formatted_streams.append({
                'itag': stream.itag,
                'resolution': stream.resolution,
                'filesize': stream.filesize,
                'fps': stream.fps,
                'type': f"{stream.mime_type.split('/')[1].upper()}"
            })
        
        return {
            'title': yt.title,
            'author': yt.author,
            'duration': yt.length,
            'thumbnail_url': yt.thumbnail_url,
            'streams': formatted_streams
        }
        
    except AgeRestrictedError:
        raise ValueError("该视频受年龄限制，无法下载")
    except VideoUnavailable:
        raise ValueError("视频不可用或已被删除")
    except Exception as e:
        logger.error(f"获取视频信息失败: {str(e)}")
        raise ValueError(f"处理视频时出错: {str(e)}")

def stream_video(video_id, itag):
    """流式传输视频数据，不存储本地文件"""
    try:
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        
        # 获取指定itag的流
        stream = yt.streams.get_by_itag(itag)
        
        if not stream:
            raise ValueError("无效的视频分辨率")
            
        # 生成安全的文件名
        safe_title = re.sub(r'[^\w\-_. ]', '', yt.title)
        filename = f"{safe_title}_{stream.resolution}.mp4"
        
        # 使用字节流下载并传输
        byte_stream = io.BytesIO()
        stream.stream_to_buffer(byte_stream)
        byte_stream.seek(0)
        
        return byte_stream, filename, stream.filesize
        
    except Exception as e:
        logger.error(f"视频流处理失败: {str(e)}")
        raise ValueError(f"处理视频时出错: {str(e)}")

# API路由: 获取视频信息
@app.route('/api/video-info', methods=['GET'])
def video_info():
    try:
        video_id = request.args.get('video_id')
        
        if not video_id:
            return jsonify({'error': '缺少视频ID参数'}), 400
            
        # 获取视频信息
        info = get_video_info(video_id)
        return jsonify(info)
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"API错误: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500

# API路由: 流式下载视频
@app.route('/api/download', methods=['GET'])
def download():
    try:
        video_id = request.args.get('video_id')
        itag = request.args.get('resolution')
        
        if not video_id or not itag:
            return jsonify({'error': '缺少必要参数'}), 400
            
        # 获取视频流
        byte_stream, filename, file_size = stream_video(video_id, itag)
        
        # 流式传输响应
        def generate():
            chunk_size = 1024 * 1024  # 1MB chunks
            while True:
                chunk = byte_stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            byte_stream.close()  # 释放资源
        
        # 设置响应头
        response = Response(
            generate(),
            mimetype="video/mp4"
        )
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-Length"] = str(file_size)
        response.headers["Accept-Ranges"] = "bytes"
        
        return response
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"下载API错误: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500

# 健康检查路由
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

# 主页路由
@app.route('/', methods=['GET'])
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube视频下载器API</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .method { display: inline-block; padding: 3px 8px; background: #4CAF50; color: white; border-radius: 3px; margin-right: 10px; }
            .get { background: #4CAF50; }
            .post { background: #2196F3; }
        </style>
    </head>
    <body>
        <h1>YouTube视频下载器API</h1>
        <p>使用以下API端点获取视频信息和下载视频</p>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span>/api/video-info</h3>
            <p>获取视频信息和可用分辨率</p>
            <p>参数: video_id - YouTube视频ID</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span>/api/download</h3>
            <p>下载指定分辨率的视频</p>
            <p>参数: video_id - YouTube视频ID, resolution - 分辨率itag值</p>
        </div>
    </body>
    </html>
    """

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'API端点不存在'}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"服务器错误: {str(error)}")
    return jsonify({'error': '服务器内部错误'}), 500

# 应用入口
if __name__ == '__main__':
    # 开发环境运行
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    )