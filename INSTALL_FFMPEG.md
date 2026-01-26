# FFmpeg 安装指南

## 当前状态
- ✅ pydub 已安装
- ❌ ffmpeg 未安装（pydub依赖ffmpeg处理音频文件）

## 快速安装方法

### 方法1：自动下载安装（推荐）

运行以下PowerShell命令：

```powershell
# 下载ffmpeg
$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$output = "$env:TEMP\ffmpeg.zip"
Invoke-WebRequest -Uri $url -OutFile $output

# 解压到C:\ffmpeg
Expand-Archive -Path $output -DestinationPath "C:\ffmpeg" -Force

# 添加到PATH（需要管理员权限）
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\ffmpeg\ffmpeg-7.1-essentials_build\bin", [EnvironmentVariableTarget]::Machine)

Write-Host "✅ ffmpeg安装完成！请重启终端使PATH生效。"
```

### 方法2：手动安装

1. 访问：https://www.gyan.dev/ffmpeg/builds/
2. 下载：ffmpeg-release-essentials.zip
3. 解压到：`C:\ffmpeg`
4. 添加到系统PATH：
   - 右键"此电脑" → 属性 → 高级系统设置
   - 环境变量 → 系统变量 → Path
   - 添加：`C:\ffmpeg\bin`
5. 重启终端验证：`ffmpeg -version`

### 方法3：使用winget（需要同意协议）

```powershell
winget install --id=Gyan.FFmpeg -e
```

## 安装后测试

```powershell
# 验证ffmpeg
ffmpeg -version

# 测试音频转换
E:\Docker\astrbot\AstrBot\.venv\Scripts\python.exe e:\Docker\bestdori\astrbot_plugin_bestdori_tools\test_pydub.py
```

## 安装完成后

重新在AstrBot中测试：
```
/bd birthday ksm
```

应该能看到语音消息发送成功！🎵
