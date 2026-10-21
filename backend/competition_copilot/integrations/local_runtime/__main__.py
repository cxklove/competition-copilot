"""Local demo entrypoint; cloud requires explicit backend environment opt-in."""

from competition_copilot.integrations.local_runtime.server import main

if __name__ == "__main__":
    main()
