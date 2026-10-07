FROM python:3.13-slim
# 时区数据：zoneinfo("Asia/Shanghai") 依赖 /usr/share/zoneinfo，slim 镜像默认没有
ENV TZ=Asia/Shanghai
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
COPY app ./app
COPY sql ./sql
RUN mkdir -p uploads
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
