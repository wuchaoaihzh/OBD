#!/data/data/com.termux/files/usr/bin/bash
# 一键启动OBD检测服务

cd ~/obd_monitor

# 检查是否已在运行
if pgrep -f "python app.py" > /dev/null; then
    echo "服务已在运行，直接打开浏览器..."
else
    echo "启动OBD检测服务..."
    nohup python app.py > ~/obd_monitor/obd.log 2>&1 &
    sleep 2
    echo "服务已启动"
fi

# 打开浏览器
am start -a android.intent.action.VIEW -d "http://localhost:5000" > /dev/null 2>&1
echo "浏览器已打开 http://localhost:5000"
