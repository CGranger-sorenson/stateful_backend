# The MIT License (MIT)
# 
# Copyright (c) 2021, NVIDIA CORPORATION. All rights reserved.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


import docker
from docker.api import network
from docker.models.containers import Container
from docker.models.images import Image
from docker.types.containers import DeviceRequest, Ulimit
import stateful_config

docker_client = None
def get_docker_client():
  global docker_client
  if docker_client is None:
    docker_client = docker.from_env()
  return docker_client

def is_custom_image_ready():
  dcl = get_docker_client()
  img: Image
  for img in dcl.images.list():
    for tag in img.tags:
      if tag == stateful_config.STATEFUL_BACKEND_IMAGE:
        return True
  return False

def is_container_ready(cnt_name:str) -> Container:
  dcl = get_docker_client()
  cnt: Container
  for cnt in dcl.containers.list(all=True, filters={"name": cnt_name}):
    if cnt_name == cnt.name:
      return cnt
  return None

def is_container_running(cnt_name:str) -> Container:
  dcl = get_docker_client()
  cnt: Container
  for cnt in dcl.containers.list(filters={"name": cnt_name, "status":"running"}):
    if cnt_name == cnt.name:
      return cnt
  return None

def get_running_container(cnt_name:str) -> Container:
  dcl = get_docker_client()
  cnt: Container
  cnt = is_container_ready(cnt_name)
  if cnt is None:
    return None
  # cnt = is_container_running(cnt_name)
  if cnt.status != 'running':
    cnt.start()
  return cnt

def create_container(img_name:str, cnt_name:str=None, auto_remove=True, \
                  with_gpus=True, ports=None, \
                  shm_size=None, memlock=None, \
                  stack_size=None, volumes=None):
  print("Creating new container:{0} from Image: {1}".format(cnt_name, img_name))
  dcl = get_docker_client()
  devs = []
  if with_gpus:
    devs.append( DeviceRequest(count=-1, capabilities=[['gpu']]) )
  
  network_mode = "host"
  if ports is not None:
    network_mode = "" ## TODO?
  
  ulimits = []
  if memlock is not None:
    ulimits.append( Ulimit(name="memlock", soft=memlock, hard=memlock) )
  if stack_size is not None:
    ulimits.append( Ulimit(name="stack", soft=stack_size, hard=stack_size) )
  
  cnt = dcl.containers.create(img_name, name=cnt_name, auto_remove=auto_remove, \
          tty=True, device_requests=devs, ports=ports, shm_size=shm_size, \
          network_mode=network_mode, ulimits=ulimits, volumes=volumes)
  return cnt
  