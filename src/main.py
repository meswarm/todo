"""Matrix runtime entrypoint."""
from __future__ import annotations


app = None  # compatibility placeholder; runtime is Matrix-only


def main() -> None:
    from src.app import main as matrix_main
    matrix_main()


if __name__ == "__main__":
    # 默认启动 Matrix-first 进程，不依赖 HTTP server
    main()
