from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


@dataclass
class AISettings:
    enabled: bool = True
    mode: str = "local"  # local | online
    local_base_url: str = "http://127.0.0.1:11434/v1"
    local_model: str = "qwen3.5:2b"
    online_base_url: str = "https://api.openai.com/v1"
    online_api_key: str = ""
    online_model: str = "gpt-4o-mini"
    timeout_seconds: int = 20


@dataclass
class AIResult:
    provider: str
    mode: str
    model: str
    summary: str
    tags: list[str]
    suggested_category: str = ""
    suggested_name: str = ""
    raw: str = ""


class AIClassifier:
    def __init__(self, settings: AISettings):
        self.settings = settings

    def analyze(self, *, file_name: str, final_name: str, file_suffix: str, final_suffix: str,
                rule_category: str, rule_reason: str, is_shortcut: bool,
                shortcut_target: str | None = None) -> AIResult:
        mode = (self.settings.mode or "local").lower()
        if mode not in {"local", "online"}:
            mode = "local"

        if mode == "local":
            model = self.settings.local_model
            if not model:
                raise RuntimeError("AI 模型未配置")
            prompt = self._build_prompt(
                file_name=file_name,
                final_name=final_name,
                file_suffix=file_suffix,
                final_suffix=final_suffix,
                rule_category=rule_category,
                rule_reason=rule_reason,
                is_shortcut=is_shortcut,
                shortcut_target=shortcut_target,
            )
            text = self._run_ollama_cli(model, prompt)
            parsed = self._parse_content(text)
            return AIResult(
                provider="ollama-cli",
                mode=mode,
                model=model,
                summary="",
                tags=[],
                suggested_category=str(parsed.get("category", "")).strip(),
                suggested_name=str(parsed.get("suggested_name", "")).strip(),
                raw=text,
            )

        base_url = self.settings.online_base_url.rstrip("/")
        model = self.settings.online_model
        api_key = self.settings.online_api_key
        if not base_url:
            raise RuntimeError("AI Base URL 未配置")
        if not model:
            raise RuntimeError("AI 模型未配置")
        if not api_key:
            raise RuntimeError("在线 AI 的 API Key 未配置")

        prompt = self._build_prompt(
            file_name=file_name,
            final_name=final_name,
            file_suffix=file_suffix,
            final_suffix=final_suffix,
            rule_category=rule_category,
            rule_reason=rule_reason,
            is_shortcut=is_shortcut,
            shortcut_target=shortcut_target,
        )

        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 200,
            "messages": [
                {"role": "system", "content": "你是中文文件重命名助手。不要解释，不要分析，不要输出思考过程。只输出一个 JSON 对象。"},
                {"role": "user", "content": prompt},
            ],
        }

        req = request.Request(
            url=f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AI 请求失败: HTTP {exc.code} {detail}") from exc
        except Exception as exc:
            raise RuntimeError(f"AI 请求失败: {exc}") from exc

        try:
            data = json.loads(body)
            text = self._extract_message_text(data)
        except Exception as exc:
            raise RuntimeError(f"AI 返回格式异常: {exc}; body={body[:500]}") from exc

        parsed = self._parse_content(text)
        return AIResult(
            provider="online-openai-compatible",
            mode=mode,
            model=model,
            summary="",
            tags=[],
            suggested_category=str(parsed.get("category", "")).strip(),
            suggested_name=str(parsed.get("suggested_name", "")).strip(),
            raw=text,
        )

    def _build_prompt(self, *, file_name: str, final_name: str, file_suffix: str, final_suffix: str,
                      rule_category: str, rule_reason: str, is_shortcut: bool,
                      shortcut_target: str | None = None) -> str:
        return "\n".join([
            "你是中文文件重命名助手。",
            "请严格只输出一个 JSON 对象，不要输出任何解释、分析、思考过程、前后缀文字。",
            "输出格式：",
            '{"category":"分类名","suggested_name":"不含扩展名的最终文件名"}',
            "规则：",
            "1. suggested_name 不含扩展名。",
            "2. 对音频文件，如果文件名中同时存在歌曲名和歌手名，必须保留‘歌曲名 - 歌手名’。",
            "3. 不要只保留歌手，不要只保留版本词，不要把加速版、伴奏、Live、Remix、Cover 等修饰词当主标题。",
            "4. 如果歌手名里有括号别名，优先保留更像真实姓名或主要名称的歌手名。",
            "5. 删除批量整理痕迹、分类前缀、时间戳、无意义下划线。",
            "6. category 只能从这些值中选择：文档、表格数据、演示文稿、图片、视频、音频、压缩包、程序快捷方式、代码开发、设计素材、其他。",
            "示例：",
            'AUDIO_三国恋_-_小野来了_20260325_153322.flac -> {"category":"音频","suggested_name":"三国恋 - 小野来了"}',
            'AUDIO_第57次取消发送（加速版）_-_菲菲公主（陆绮菲）_20260325_153332.flac -> {"category":"音频","suggested_name":"第57次取消发送 - 陆绮菲"}',
            'DATA_豆瓣_Top_250_20260325_153334.xlsx -> {"category":"表格数据","suggested_name":"豆瓣Top250电影榜单"}',
            f"原始文件名: {file_name}",
            f"最终目标文件名: {final_name}",
            f"原始扩展名: {file_suffix or '(无)'}",
            f"最终扩展名: {final_suffix or '(无)'}",
            f"是否快捷方式: {'是' if is_shortcut else '否'}",
            f"快捷方式真实目标: {shortcut_target or '无'}",
            f"规则分类结果: {rule_category}",
            f"规则分类理由: {rule_reason}",
        ])

    def _run_ollama_cli(self, model: str, prompt: str) -> str:
        try:
            completed = subprocess.run(
                ["ollama", "run", model, "--think=false"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.settings.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("未找到 ollama 命令，请确认已安装并加入 PATH") from exc
        except Exception as exc:
            raise RuntimeError(f"调用 ollama 失败: {exc}") from exc

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if completed.returncode != 0:
            raise RuntimeError(f"ollama 执行失败: {stderr or stdout or ('exit=' + str(completed.returncode))}")
        if not stdout:
            raise RuntimeError(f"ollama 未返回内容: {stderr or 'stdout 为空'}")
        return stdout

    @staticmethod
    def _extract_message_text(data: dict[str, Any]) -> str:
        message = data["choices"][0]["message"]
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return str(content or "")

    @staticmethod
    def _parse_content(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            candidate = match.group(0)
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        raise RuntimeError(f"AI 返回不是合法 JSON；text={text[:500]}")


def settings_to_dict(settings: AISettings) -> dict[str, Any]:
    return asdict(settings)


def settings_from_dict(data: dict[str, Any] | None) -> AISettings:
    data = data or {}
    return AISettings(
        enabled=bool(data.get("enabled", True)),
        mode=str(data.get("mode", "local") or "local"),
        local_base_url=str(data.get("local_base_url", "http://127.0.0.1:11434/v1") or "http://127.0.0.1:11434/v1"),
        local_model=str(data.get("local_model", "qwen3.5:2b") or "qwen3.5:2b"),
        online_base_url=str(data.get("online_base_url", "https://api.openai.com/v1") or "https://api.openai.com/v1"),
        online_api_key=str(data.get("online_api_key", "") or ""),
        online_model=str(data.get("online_model", "gpt-4o-mini") or "gpt-4o-mini"),
        timeout_seconds=int(data.get("timeout_seconds", 20) or 20),
    )


def load_ai_settings(path: Path) -> AISettings:
    if not path.exists():
        return AISettings()
    try:
        return settings_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return AISettings()


def save_ai_settings(path: Path, settings: AISettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings_to_dict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
