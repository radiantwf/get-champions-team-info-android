import shutil
import subprocess
import sys
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import uiautomator2 as u2

from src.teamid.team import Team


DEFAULT_RETRY_INTERVAL_SECONDS = 3
MAX_ASYNC_WORKERS = 3


def force_update_ocr_models():
    """
    删除当前使用的 OCR 模型并强制重新安装/下载。
    EasyOCR 模型在下次 Reader 初始化时自动下载；RapidOCR 模型随包分发，需要强制重装包。
    """
    easyocr_model_dir = Path.home() / ".EasyOCR" / "model"
    if easyocr_model_dir.exists():
        print(f"删除 EasyOCR 模型目录: {easyocr_model_dir}")
        shutil.rmtree(easyocr_model_dir)

    try:
        import rapidocr_onnxruntime
        rapidocr_model_dir = Path(rapidocr_onnxruntime.__file__).resolve().parent / "models"
    except Exception as e:
        raise RuntimeError(f"无法定位 RapidOCR 模型目录: {e}") from e

    if rapidocr_model_dir.exists():
        print(f"删除 RapidOCR 模型目录: {rapidocr_model_dir}")
        shutil.rmtree(rapidocr_model_dir)

    print("强制重新安装 rapidocr_onnxruntime 以更新 RapidOCR 模型")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "--no-deps",
            "rapidocr_onnxruntime",
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "rapidocr_onnxruntime 强制重装失败，RapidOCR 模型可能已被删除。\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    try:
        from src.ocr.easy import EasyOCR
        EasyOCR._instance = None
    except Exception:
        pass


def create_pokepaste_until_success(
    paste_text: str,
    title: str,
    author: str = "OCR",
    pokepaste_retry_interval_seconds: int = DEFAULT_RETRY_INTERVAL_SECONDS,
) -> str:
    while True:
        try:
            data = urllib.parse.urlencode({
                "paste": paste_text,
                "title": title,
                "author": author,
            }).encode("utf-8")
            req = urllib.request.Request("https://pokepast.es/create", data=data)
            resp = urllib.request.urlopen(req, timeout=10)
            if resp.url and resp.url.rstrip("/") != "https://pokepast.es/create":
                return resp.url
            print(f"生成 Pokepaste 失败: 响应 URL 无效 ({resp.url})，准备重试")
        except Exception as e:
            print(f"生成 Pokepaste 失败: {e}，{pokepaste_retry_interval_seconds} 秒后重试")
        time.sleep(pokepaste_retry_interval_seconds)


def _normalize_rental_codes(rental_codes):
    if isinstance(rental_codes, str):
        return [code.strip() for code in rental_codes.replace(",", "\n").splitlines() if code.strip()]
    return [str(code).strip() for code in rental_codes if str(code).strip()]


def _safe_code_for_path(rental_code: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in rental_code)


def _new_log_path(rental_codes):
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if len(rental_codes) == 1:
        filename = f"teamid_{_safe_code_for_path(rental_codes[0])}_{timestamp}.log"
    else:
        filename = f"teamid_batch_{timestamp}.log"
    return output_dir / filename


def _format_log_section(rental_code: str, team: Team | None, pokepaste_url: str | None, error: str | None = None):
    lines = [
        "=" * 60,
        f"租借码: {rental_code}",
        f"Pokepaste URL: {pokepaste_url or ''}",
        "OCR识别为空日志:",
    ]
    if team is None:
        lines.append("未生成队伍，无法读取错误日志")
    else:
        lines.extend(team.ocr_errors if team.ocr_errors else ["无"])

    lines.extend([
        "中英文转换错误日志:",
    ])
    if team is None:
        lines.append("未生成队伍，无法读取错误日志")
    else:
        lines.extend(team.conversion_errors if team.conversion_errors else ["无"])

    lines.extend([
        "努力值66检查错误日志:",
    ])
    if team is None:
        lines.append("未生成队伍，无法读取错误日志")
    else:
        lines.extend(team.ev_errors if team.ev_errors else ["无"])

    if error:
        lines.extend([
            "处理错误:",
            error,
        ])
    lines.append("")
    return "\n".join(lines)


def write_process_log(rental_code: str, team: Team, pokepaste_url: str):
    log_path = _new_log_path([rental_code])
    log_path.write_text(_format_log_section(rental_code, team, pokepaste_url), encoding="utf-8")
    return log_path


def _append_batch_log(log_path: Path, lock: threading.Lock, rental_code: str, team: Team | None, pokepaste_url: str | None, error: str | None = None):
    section = _format_log_section(rental_code, team, pokepaste_url, error=error)
    with lock:
        with log_path.open("a", encoding="utf-8") as file:
            file.write(section)
            file.write("\n")


def _resolve_future_result(rental_code: str, future):
    try:
        team, pokepaste_url = future.result()
        return team, pokepaste_url, None
    except Exception as e:
        error = f"租借码 {rental_code} 后台处理失败: {e}"
        return None, None, error


def _write_batch_result(log_path: Path, log_lock: threading.Lock, rental_code: str, result):
    team, pokepaste_url, error = result
    _append_batch_log(log_path, log_lock, rental_code, team, pokepaste_url, error=error)
    if error:
        print(error)
    else:
        print(f"租借码: {rental_code}")
        print(f"Pokepaste URL: {pokepaste_url}")


def _store_ordered_future_result(
    index: int,
    rental_code: str,
    future,
    condition: threading.Condition,
    pending_results: dict,
):
    result = _resolve_future_result(rental_code, future)
    with condition:
        pending_results[index] = result
        condition.notify_all()


def _write_ordered_results(
    codes,
    log_path: Path,
    log_lock: threading.Lock,
    condition: threading.Condition,
    pending_results: dict,
    state: dict,
):
    while True:
        with condition:
            while (
                state["next_output"] not in pending_results
                and not (
                    state["capture_done"]
                    and state["next_output"] >= state["submitted_count"]
                )
            ):
                condition.wait()

            if (
                state["capture_done"]
                and state["next_output"] >= state["submitted_count"]
                and state["next_output"] not in pending_results
            ):
                return

            index = state["next_output"]
            result = pending_results.pop(index)
            state["next_output"] += 1
            condition.notify_all()

        _write_batch_result(log_path, log_lock, codes[index], result)


def _device_shell_output(d, cmd):
    result = d.shell(cmd)
    if result.exit_code != 0:
        raise RuntimeError(f"手机 shell 命令执行失败: {cmd}, exit_code={result.exit_code}")
    return result.output or ""


def _is_device_unlocked(d):
    trust_output = _device_shell_output(d, ["dumpsys", "trust"])
    trust_match = re.search(r"\bdeviceLocked\s*=\s*(true|false)\b", trust_output, re.IGNORECASE)
    if trust_match:
        return trust_match.group(1).lower() == "false"

    window_output = _device_shell_output(d, ["dumpsys", "window"])
    lockscreen_signals = [
        r"\bmShowingLockscreen\s*=\s*true\b",
        r"\bmDreamingLockscreen\s*=\s*true\b",
        r"\bisStatusBarKeyguard\s*=\s*true\b",
        r"\bmInputRestricted\s*=\s*true\b",
    ]
    if any(re.search(pattern, window_output, re.IGNORECASE) for pattern in lockscreen_signals):
        return False

    unlocked_signals = [
        r"\bmShowingLockscreen\s*=\s*false\b",
        r"\bmDreamingLockscreen\s*=\s*false\b",
        r"\bisStatusBarKeyguard\s*=\s*false\b",
    ]
    if any(re.search(pattern, window_output, re.IGNORECASE) for pattern in unlocked_signals):
        return True

    screen_on = getattr(d, "info", {}).get("screenOn")
    if screen_on is False:
        return False

    raise RuntimeError("无法判断手机是否已解锁，请手动解锁手机后重试")


def _require_device_unlocked(d):
    if not _is_device_unlocked(d):
        raise RuntimeError("手机未解锁，请先解锁手机后重新运行")


def _start_device_once():
    d = u2.connect()
    _require_device_unlocked(d)
    d.app_start("jp.pokemon.pokemonchampions")
    time.sleep(2)
    return d


def _capture_rental_images(d, rental_code: str):
    d.click(2380, 60)
    time.sleep(0.8)
    d.click(1053, 622)
    time.sleep(3)
    d.click(1678, 652)
    time.sleep(0.8)
    d.click(1782, 528)
    time.sleep(2)
    d.click(494, 632)
    time.sleep(0.5)
    d.click(565, 673)
    time.sleep(0.5)
    d.click(1530, 1043)
    time.sleep(0.8)
    d.click(1318, 575)
    time.sleep(0.8)
    d.xpath('//android.widget.EditText').set_text(rental_code)
    time.sleep(0.5)
    d.xpath('//android.widget.Button').click()
    d.click(1572, 824)
    time.sleep(2)
    image1 = d.screenshot(format='opencv')
    d.click(1520, 240)
    time.sleep(1)
    image2 = d.screenshot(format='opencv')
    return image1, image2


def _process_images(
    rental_code: str,
    image1,
    image2,
    offsets_y: int,
    pokepaste_retry_interval_seconds: int,
    output_dir: str,
    save_images: bool,
):
    team = Team(offsets_y=offsets_y, output_dir=output_dir, save_images=save_images)
    team.process_moves_image(image1)
    team.process_states_image(image2)
    pokepaste_url = create_pokepaste_until_success(
        str(team),
        title=f"OCR Team {rental_code}",
        author="OCR",
        pokepaste_retry_interval_seconds=pokepaste_retry_interval_seconds,
    )
    return team, pokepaste_url


def process(
    rental_code: str,
    offsets_y: int = 0,
    pokepaste_retry_interval_seconds: int = DEFAULT_RETRY_INTERVAL_SECONDS,
    force_update_models: bool = False,
):
    log_path = process_batch(
        [rental_code],
        offsets_y=offsets_y,
        pokepaste_retry_interval_seconds=pokepaste_retry_interval_seconds,
        force_update_models=force_update_models,
    )
    return log_path


def process_batch(
    rental_codes,
    offsets_y: int = 0,
    pokepaste_retry_interval_seconds: int = DEFAULT_RETRY_INTERVAL_SECONDS,
    force_update_models: bool = False,
):
    codes = _normalize_rental_codes(rental_codes)
    if not codes:
        raise ValueError("租借码列表为空")

    if force_update_models:
        force_update_ocr_models()

    log_path = _new_log_path(codes)
    log_path.write_text("", encoding="utf-8")
    log_lock = threading.Lock()
    ordered_condition = threading.Condition()
    pending_results = {}
    ordered_state = {
        "next_output": 0,
        "submitted_count": 0,
        "capture_done": False,
    }
    save_images = len(codes) == 1

    d = _start_device_once()
    executor = ThreadPoolExecutor(max_workers=MAX_ASYNC_WORKERS)
    writer_thread = threading.Thread(
        target=_write_ordered_results,
        args=(
            codes,
            log_path,
            log_lock,
            ordered_condition,
            pending_results,
            ordered_state,
        ),
    )
    writer_thread.start()
    try:
        for index, rental_code in enumerate(codes):
            print(f"开始读取租借码: {rental_code}")
            image1, image2 = _capture_rental_images(d, rental_code)
            output_dir = "./outputs"
            future = executor.submit(
                _process_images,
                rental_code,
                image1,
                image2,
                offsets_y,
                pokepaste_retry_interval_seconds,
                output_dir,
                save_images,
            )
            with ordered_condition:
                ordered_state["submitted_count"] = index + 1
                ordered_condition.notify_all()
            future.add_done_callback(
                lambda completed_future, task_index=index, code=rental_code: _store_ordered_future_result(
                    task_index,
                    code,
                    completed_future,
                    ordered_condition,
                    pending_results,
                )
            )
            print(f"已提交后台处理: {rental_code}")
    finally:
        d.screen_off()
        with ordered_condition:
            ordered_state["capture_done"] = True
            ordered_condition.notify_all()
        executor.shutdown(wait=True)
        writer_thread.join()

    print(f"批量日志文件: {log_path}")
    return log_path
