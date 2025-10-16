"""Quick hardware evaluation helper."""

from whispermeeting import build_container


def main() -> None:
    container = build_container()
    profile = container.hardware_profiler.to_dict()
    for key, value in profile.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
