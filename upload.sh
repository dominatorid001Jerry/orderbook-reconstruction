#!/bin/bash
# Git Bash 完整上传脚本
# 在 Git Bash 中运行

echo "=========================================="
echo "  开始上传到 GitHub"
echo "=========================================="
echo ""

# 1. 检查是否在正确的目录
pwd

# 2. 删除旧的 Git 配置（如果有）
echo "清理旧配置..."
rm -rf .git

# 3. 重新初始化
echo "初始化 Git 仓库..."
git init

# 4. 添加所有文件
echo "添加文件..."
git add .

# 5. 提交
echo "提交..."
git commit -m "Clean version: Core code and documentation only"

# 6. 添加远程仓库
echo "连接到 GitHub..."
git remote add origin https://github.com/dominatorid001Jerry/orderbook-reconstruction.git

# 7. 重命名分支
echo "设置主分支..."
git branch -M main

# 8. 强制推送
echo "推送到 GitHub..."
git push -f origin main

echo ""
echo "=========================================="
echo "  完成！"
echo "=========================================="
echo ""
echo "访问你的仓库："
echo "https://github.com/dominatorid001Jerry/orderbook-reconstruction"
