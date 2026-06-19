# Pokemon Champions 租借队识别

本项目用于通过 Android 手机截图识别 Pokemon Champions 租借队伍，生成 Pokepaste 链接，并输出处理日志。

## 测试环境

- 测试手机：一加 13T
- 当前连接手机分辨率：

```text
Physical size: 1216x2640
```

分辨率获取命令：

```bash
adb shell wm size
```

## 安装依赖

```bash
./prepare.sh
```

或手动安装：

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 运行

在 [main.py](main.py) 中配置租借码：

```python
RENTAL_CODES = [
    "SGLT1AAJWS",
    "BMYR5TU6TP",
]
```

运行：

```bash
venv/bin/python main.py
```

## 批量处理说明

- `process_batch` 支持一次传入多个租借码。
- 手机连接和 `app_start` 只执行一次。
- 手机操作线程会依次读取所有租借码截图。
- OCR、努力值识别、Pokepaste 上传、日志写入会异步执行。
- 异步处理最多同时运行 3 个后台任务。
- 手机读取完所有租借码后会执行 `screen_off()`。
- 多个租借码批量处理时，只生成一个批量日志文件。

日志文件位置：

```text
outputs/teamid_<租借码>_<时间>.log
outputs/teamid_batch_<时间>.log
```

日志包含：

- 租借码
- Pokepaste URL
- 中英文转换错误日志
- 努力值 66 检查错误日志

## 图片输出规则

- 只有租借码数量为 1 时才生成中间图片。
- 多个租借码批量处理时不生成 OCR 中间图片。
- 单个租借码时沿用原图片命名规则：

```text
outputs/team_basic.png
outputs/team_states.png
outputs/poke{i}.png
outputs/poke{i}_stats.png
outputs/poke{i}/name.png
outputs/poke{i}/ability.png
outputs/poke{i}/item.png
outputs/poke{i}/move1.png
outputs/poke{i}/move2.png
outputs/poke{i}/move3.png
outputs/poke{i}/move4.png
outputs/poke{i}/gender.png
outputs/poke{i}/type1.png
outputs/poke{i}/type2.png
outputs/poke{i}/poke.png
outputs/poke{i}/stat_hp.png
outputs/poke{i}/stat_atk.png
outputs/poke{i}/stat_def.png
outputs/poke{i}/stat_spa.png
outputs/poke{i}/stat_spd.png
outputs/poke{i}/stat_spe.png
outputs/poke{i}/stat_atk_modify.png
```

## 坐标与模板适配

当前坐标基于测试设备一加 13T，分辨率 `1216x2640`。如果更换手机、模拟器、系统缩放、游戏显示比例或截图分辨率，需要重新获取坐标和模板文件。

需要检查或重新采集的坐标位置：

- 手机点击流程：[src/teamid/__init__.py](src/teamid/__init__.py)
  - `_capture_rental_images`
  - 包括进入租借队页面、输入租借码、确认、切换 basic/stats 页面等点击坐标。
- 队伍六只宝可梦的大区域裁剪：[src/teamid/team.py](src/teamid/team.py)
  - `REGION_WIDTH`
  - `REGION_HEIGHT`
  - `_split_pokemon` 中 6 个宝可梦区域左上角坐标。
- 单只宝可梦 basic 信息裁剪：[src/teamid/pokemon.py](src/teamid/pokemon.py)
  - `process_moves_image` 中 `name / ability / item / move1..move4 / gender / type1 / type2 / poke` 的 ROI 坐标。
- 单只宝可梦 stats 信息裁剪：[src/teamid/pokemon.py](src/teamid/pokemon.py)
  - `process_states_image` 中 `hp / atk / def / spa / spd / spe` 和 `stat_atk_modify` 的 ROI 坐标。

需要检查或重新采集的模板文件：

```text
resources/imgs/teamid/stat_modify/up.png
resources/imgs/teamid/stat_modify/down.png
resources/imgs/teamid/gender/female.png
resources/imgs/teamid/type/*.png
resources/imgs/teamid/pokemon/<PokemonName>/*.png
```

模板用途：

- `stat_modify/up.png`、`stat_modify/down.png`：识别性格升降项箭头。
- `gender/female.png`：识别雌性形态规则。
- `type/*.png`：识别属性图标，用于地区形态判断。
- `pokemon/<PokemonName>/*.png`：识别同名不同形态。

## 坐标重新采集建议

1. 先确认手机分辨率：

```bash
adb shell wm size
```

2. 单租借码运行一次，让程序生成中间图片。
3. 使用 `outputs/team_basic.png` 和 `outputs/team_states.png` 重新标注：
   - 六只宝可梦外框区域
   - basic 字段 ROI
   - stats 数字 ROI
4. 更新 `src/teamid/team.py` 和 `src/teamid/pokemon.py` 中的坐标。
5. 如果模板匹配失败，重新截取对应模板并覆盖 `resources/imgs/teamid/...` 下的文件。
6. 再次运行单租借码验证，确认：
   - OCR 识别正确
   - 中英文映射正确
   - EV 总和为 66
   - Pokepaste URL 正常生成

## OCR 模型强制更新

在 [main.py](main.py) 中设置：

```python
FORCE_UPDATE_MODELS = True
```

运行时会删除当前 EasyOCR 模型缓存，并强制重装 `rapidocr_onnxruntime` 以恢复 RapidOCR 包内模型。正常使用时建议保持：

```python
FORCE_UPDATE_MODELS = False
```
