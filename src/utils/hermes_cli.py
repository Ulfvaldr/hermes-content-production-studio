import os
import subprocess


DEFAULT_TIMEOUT_SECONDS = 300


def extract_balanced_json_object(text, start):
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return None


def run_hermes_profile(profile, prompt, timeout=DEFAULT_TIMEOUT_SECONDS):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["NO_COLOR"] = "1"

    try:
        result = subprocess.run(
            [
                "hermes",
                "-p",
                profile,
                "chat",
                "--oneshot",
                "--quiet",
                "--query-file",
                "-",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"Hermes profile '{profile}' timed out after {timeout} seconds"
        ) from exc

    result.stdout = (result.stdout or "").strip()
    return result
