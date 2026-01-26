# 自动安装ffmpeg脚本
Write-Host "开始下载ffmpeg..." -ForegroundColor Cyan

$url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
$output = "$env:TEMP\ffmpeg.zip"
$extractPath = "C:\ffmpeg"

try {
    # 下载
    Write-Host "下载中..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $url -OutFile $output -UseBasicParsing
    
    # 解压
    Write-Host "解压中..." -ForegroundColor Yellow
    if (Test-Path $extractPath) {
        Remove-Item $extractPath -Recurse -Force
    }
    Expand-Archive -Path $output -DestinationPath $extractPath -Force
    
    # 找到bin目录
    $binPath = Get-ChildItem -Path $extractPath -Filter "bin" -Recurse -Directory | Select-Object -First 1
    
    if ($binPath) {
        $ffmpegBin = $binPath.FullName
        Write-Host "ffmpeg位置: $ffmpegBin" -ForegroundColor Green
        
        # 添加到用户PATH（不需要管理员权限）
        $currentPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
        if ($currentPath -notlike "*$ffmpegBin*") {
            [Environment]::SetEnvironmentVariable("Path", $currentPath + ";$ffmpegBin", [EnvironmentVariableTarget]::User)
            Write-Host "✅ 已添加到用户PATH" -ForegroundColor Green
        }
        
        # 刷新当前会话的PATH
        $env:Path += ";$ffmpegBin"
        
        # 验证安装
        Write-Host "`n验证安装..." -ForegroundColor Cyan
        & "$ffmpegBin\ffmpeg.exe" -version | Select-Object -First 1
        
        Write-Host "`n✅ ffmpeg安装成功！" -ForegroundColor Green
        Write-Host "请重启PowerShell窗口使PATH永久生效。" -ForegroundColor Yellow
    } else {
        Write-Host "❌ 未找到bin目录" -ForegroundColor Red
    }
    
    # 清理
    Remove-Item $output -Force
    
} catch {
    Write-Host "❌ 安装失败: $_" -ForegroundColor Red
}
