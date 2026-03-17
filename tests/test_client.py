from __future__ import annotations

from frontend.tcp_pygame_client import TcpPygameClient


def main():
    app = TcpPygameClient(
        host="127.0.0.1",
        port=8765,
        scale=2,
        window_title="MultiEmu TCP Client",
    )
    app.run()


if __name__ == "__main__":
    main()
