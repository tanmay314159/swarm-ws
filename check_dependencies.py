#!/usr/bin/env python3
"""Check the installed swarm runtime, graphics renderer, and CUDA inference."""

import importlib
from importlib.metadata import version
import subprocess
import sys


def main():
    """Exercise dependencies using the same environment as the ROS nodes."""
    modules = [
        "rclpy", "launch_ros", "ros_gz_sim", "cv2", "numpy", "scipy",
        "matplotlib", "flask", "torch", "torchvision",
        "segmentation_models_pytorch", "transformers",
    ]
    failed = []
    for name in modules:
        try:
            module = importlib.import_module(name)
            installed_version = (
                version("flask") if name == "flask"
                else getattr(module, "__version__", "installed")
            )
            print(f"OK {name}: {installed_version}")
        except Exception as exc:
            print(f"FAIL {name}: {exc}")
            failed.append(name)
    if failed:
        print("Source setup_env.sh and install requirements.txt before checking.")
        return 1

    for command in (["gz", "sim", "--versions"], ["glxinfo", "-B"]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            print(f"FAIL {' '.join(command)}: {result.stderr.strip()}")
            return 1
        if command[0] == "gz":
            print(f"OK Gazebo Sim: {result.stdout.strip()}")
        else:
            renderer = next(
                (line for line in result.stdout.splitlines()
                 if line.startswith("OpenGL renderer string:")), ""
            )
            print(renderer)
            if "NVIDIA" not in renderer or "llvmpipe" in renderer.lower():
                print("FAIL NVIDIA hardware rendering is not active.")
                return 1
            print("OK NVIDIA OpenGL rendering")

    import numpy as np
    import torch
    from ament_index_python.packages import get_package_share_directory
    from damage_detection.infer import InferenceEngine
    from pathlib import Path

    if not torch.cuda.is_available():
        print("FAIL CUDA is unavailable to PyTorch.")
        return 1
    print(f"OK CUDA {torch.version.cuda}: {torch.cuda.get_device_name(0)}")
    tensor = torch.ones((256, 256), device="cuda")
    assert torch.all(tensor @ tensor == 256).item()
    torch.cuda.synchronize()
    print("OK CUDA matrix computation")

    checkpoint = (
        Path(get_package_share_directory("damage_detection"))
        / "checkpoints" / "sim_finetuned.pt"
    )
    engine = InferenceEngine(str(checkpoint), device="cuda")
    probabilities = engine.infer(np.zeros((480, 640, 3), dtype=np.uint8))
    assert probabilities.shape == (480, 640)
    assert np.isfinite(probabilities).all()
    print(f"OK shipped {engine.model_type} checkpoint inference on CUDA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
