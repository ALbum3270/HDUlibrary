# 杭州电子科技大学图书馆抢座脚本

## 脚本介绍

本脚本用于杭电图书馆自习室座位预约，目前支持自动登录、批量预约、定时预约等功能，有以下模块：

* 查看/添加/删除待选座位方案
* 批量修改方案中预约时间
* 定时抢座
* 图形化界面

**本脚本仅限用于个人图书馆预约座位，请勿恶意囤座位！**

**截至2026-08-16本脚本还可正常使用**

## 运行说明

0. 本脚本基于Python 3.14编写，请先安装Python 3.14。
1. 克隆本项目

``` shell
git clone https://github.com/stormmmg/HDU-Library-SeatHunter.git
cd HDU-Library-SeatHunter
```

2. 安装依赖项

```shell
pip install -r requirements.txt
```

3. 运行脚本

``` shell
python main.py
```

4. 构建 exe

```
python build.py
```

## GitHub Actions 自动预约

项目内置了 `.github/workflows/book-seat.yml`。工作流每天北京时间 19:45
启动，在 GitHub Runner 内等待到配置的开放时间，预约两天后的座位，然后自动退出。

1. 先在本地运行 GUI，完成登录并添加真实的预约方案和调度。
2. 将本地 `config/config.yaml` 中的 `plans`、`schedules` 复制到
   `config/ci.yaml`，清空其中的 `login_name` 和 `password`。
3. 检查 `config/ci.yaml` 中不存在“替换为……”占位文本，然后把调度的
   `enabled` 改为 `true` 并推送到 GitHub。
4. 在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 添加：
   - `SCHOOL_ID`：学号
   - `PASSWORD`：统一身份认证密码
5. 在仓库 `Actions` 页面启用工作流，并先用 `Run workflow` 手动验证一次。

工作流的 cron 显式使用 `Asia/Shanghai` 时区。
`config/ci.yaml` 只保存座位和调度，不应提交账号、密码或 Cookie。

> GitHub 定时任务可能延迟。`--once` 模式如果在开放时间之后才启动，会立即
> 尝试预约；没有匹配两天后日期的已启用调度时会正常退出，不发送预约请求。

最后根据软件提示登录、查看使用说明。

本脚本基于https://github.com/LittleHeroZZZX/hdu-library-killer改进

最后请各位善用脚本，祝愿各位校友前途似锦，终成所愿。
