"""Print local simulated sensor values for development self-testing."""

import argparse

from device_agent.sensor import read_measurement


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and print a local sensor value.")
    parser.add_argument(
        "parameter",
        nargs="?",
        default="oxygen_saturation",
        help="Sensor parameter, for example oxygen_saturation or systolic_bp.",
    )
    args = parser.parse_args()
    value = read_measurement(args.parameter)
    print(f"Sensor parameter: {args.parameter}")
    print(f"Sensor value: {value}")


if __name__ == "__main__":
    main()