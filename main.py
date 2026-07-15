from app.startup.bootstrap import bootstrap_app


def main() -> None:
    app = bootstrap_app()
    print(f"English Agent initialized in phase: {app['phase']}")


if __name__ == "__main__":
    main()
