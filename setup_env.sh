#!/usr/bin/env bash
# Source this file from any directory before building or launching the swarm.

_swarm_root="$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")"
if [[ -f /opt/ros/lyrical/setup.bash ]]; then
    source /opt/ros/lyrical/setup.bash
elif [[ -f /opt/ros/jazzy/setup.bash ]]; then
    source /opt/ros/jazzy/setup.bash
else
    printf 'ROS 2 Lyrical or Jazzy is not installed.\n' >&2
    return 1
fi

source "${_swarm_root}/venv/bin/activate"
if [[ -f "${_swarm_root}/install/local_setup.bash" ]]; then
    source "${_swarm_root}/install/local_setup.bash"
fi

export LIBGL_ALWAYS_SOFTWARE=0
export QT_QPA_PLATFORM=xcb
if [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
    # WSLg renders through Mesa/D3D12 and the Windows NVIDIA driver.
    export GALLIUM_DRIVER=d3d12
    export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
    export LD_LIBRARY_PATH="/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    unset __NV_PRIME_RENDER_OFFLOAD __GLX_VENDOR_LIBRARY_NAME
else
    export __NV_PRIME_RENDER_OFFLOAD=1
    export __GLX_VENDOR_LIBRARY_NAME=nvidia
fi
unset _swarm_root
