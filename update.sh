#!/data/data/com.termux/files/usr/bin/bash
# 自动从GitHub拉取最新版本

REPO="https://github.com/wuchaoaihzh/OBD"
RAW="https://raw.githubusercontent.com/wuchaoaihzh/OBD/main"
ZIP_URL="https://github.com/wuchaoaihzh/OBD/archive/refs/heads/main.zip"

echo "=============================="
echo "  新能源OBD 自动更新"
echo "=============================="

# 检查网络
if ! curl -s --max-time 5 https://github.com > /dev/null; then
    echo "❌ 无法连接GitHub，请检查网络后重试"
    exit 1
fi

# 获取远程版本号
REMOTE_VER=$(curl -s --max-time 10 "$RAW/version.txt" 2>/dev/null | tr -d '[:space:]')
LOCAL_VER=""
if [ -f ~/obd_monitor/version.txt ]; then
    LOCAL_VER=$(cat ~/obd_monitor/version.txt | tr -d '[:space:]')
fi

echo "本地版本: ${LOCAL_VER:-未知}"
echo "最新版本: ${REMOTE_VER:-未知}"

if [ -n "$REMOTE_VER" ] && [ "$REMOTE_VER" = "$LOCAL_VER" ]; then
    echo "✅ 已是最新版本，无需更新"
    exit 0
fi

echo "开始下载最新版本..."

# 停止正在运行的服务
if pgrep -f "python app.py" > /dev/null; then
    echo "停止当前服务..."
    pkill -f "python app.py"
    sleep 1
fi

# 下载zip包
cd ~
curl -L --max-time 60 -o obd_update.zip "$ZIP_URL"
if [ $? -ne 0 ]; then
    echo "❌ 下载失败，请重试"
    exit 1
fi

# 备份当前版本
if [ -d ~/obd_monitor ]; then
    cp -r ~/obd_monitor ~/obd_monitor_backup
    echo "已备份当前版本到 ~/obd_monitor_backup"
fi

# 解压并替换
unzip -o obd_update.zip -d ~/obd_tmp > /dev/null
if [ $? -ne 0 ]; then
    echo "❌ 解压失败，恢复备份..."
    rm -rf ~/obd_monitor
    mv ~/obd_monitor_backup ~/obd_monitor
    exit 1
fi

# 移动文件（GitHub zip解压后目录名是 OBD-main）
rm -rf ~/obd_monitor
mv ~/obd_tmp/OBD-main ~/obd_monitor
rm -rf ~/obd_tmp ~/obd_update.zip

echo "✅ 更新完成！版本: $REMOTE_VER"
echo "重新启动服务..."

# 重新启动
cd ~/obd_monitor
nohup python app.py > ~/obd_monitor/obd.log 2>&1 &
sleep 2

am start -a android.intent.action.VIEW -d "http://localhost:5000" > /dev/null 2>&1
echo "🚀 服务已重启，浏览器已打开"
