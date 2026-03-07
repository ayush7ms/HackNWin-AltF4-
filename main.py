"""
CLI entry point for UPSMS: --video path or --webcam to run the pipeline.
"""
import argparse

from app import run


def main():
    parser = argparse.ArgumentParser(
        description="Unified Public Safety Monitoring System (UPSMS) – video/webcam incident detection",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--video",
        type=str,
        metavar="PATH",
        help="Path to video file to process",
    )
    group.add_argument(
        "--webcam",
        action="store_true",
        help="Use default webcam (device 0)",
    )
    args = parser.parse_args()
    if args.webcam:
        source = 0
    else:
        source = args.video
    run(source)


if __name__ == "__main__":
    main()
