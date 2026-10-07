FROM python:slim

ENV NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute
ENV WGPU_FORCE_OFFSCREEN=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libvulkan1 libegl1 vulkan-tools \
    && rm -rf /var/lib/apt/lists/*

# the one pinned pair: the last wgpu with its own canvases, and the shadertoy release written against it
RUN pip install --no-cache-dir wgpu==0.23.0 wgpu-shadertoy==0.2.0 numpy pillow
