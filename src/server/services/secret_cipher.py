"""运行时配置密钥保护。"""

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecretCipher:
    """使用 Fernet 加密运行时配置 payload。

    优先使用 ``CONFIG_ENCRYPTION_KEY``。未配置时在数据目录生成仅供本机
    使用的持久密钥，保证本地部署开箱即用且重启后仍能解密。
    """

    def __init__(self, key: str | bytes):
        raw_key = key.encode("utf-8") if isinstance(key, str) else key
        try:
            self._fernet = Fernet(raw_key)
        except (ValueError, TypeError):
            derived = base64.urlsafe_b64encode(hashlib.sha256(raw_key).digest())
            self._fernet = Fernet(derived)

    @classmethod
    def from_environment(cls, storage_dir: str | Path) -> "SecretCipher":
        configured = os.getenv("CONFIG_ENCRYPTION_KEY", "").strip()
        if configured:
            return cls(configured)

        key_path = Path(storage_dir).expanduser() / ".runtime-config.key"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if not key_path.exists():
            generated = Fernet.generate_key()
            try:
                descriptor = os.open(
                    key_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                pass
            else:
                try:
                    os.write(descriptor, generated)
                finally:
                    os.close(descriptor)
        return cls(key_path.read_bytes().strip())

    @classmethod
    def ephemeral(cls) -> "SecretCipher":
        """用于内存仓库，进程退出后不需要再次解密。"""
        return cls(Fernet.generate_key())

    def encrypt_json(self, value: dict) -> str:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return self._fernet.encrypt(raw.encode("utf-8")).decode("ascii")

    def decrypt_json(self, value: str) -> dict:
        try:
            raw = self._fernet.decrypt(value.encode("ascii"))
        except (InvalidToken, ValueError, UnicodeError) as exc:
            raise ValueError("运行时配置无法解密，请检查 CONFIG_ENCRYPTION_KEY") from exc
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("运行时配置 payload 必须是对象")
        return decoded
