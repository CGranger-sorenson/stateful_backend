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


import os
import sys
import threading
import time

import stateful_utils
import stateful_config
import build_backend

g_server_started = False
g_server_exited = False
g_server_thread = None

TRITON_VOLUMES = {}
TRITON_VOL_SRC = ''
def setup_env(root_dir):
  global TRITON_VOL_SRC, TRITON_VOLUMES
  TRITON_VOL_SRC = root_dir
  TRITON_VOLUMES[TRITON_VOL_SRC] = {
    'bind': stateful_config.TRITON_VOL_DEST, 'mode': 'rw'
  }
  return

def run_server_thread_func(cnt):
  status = cnt.exec_run(stateful_config.TRITON_SERVER_CMD, stream=True, environment=stateful_config.TRITON_SERVER_ENV)
  outgen = status[1]
  global g_server_started, g_server_exited
  g_server_started = g_server_exited = False
  for ln in outgen:
    print(ln.decode(), end='')
    if ln.decode().find("Started GRPCInferenceService") >= 0:
      g_server_started = True
    if ln.decode().find("successfully unloaded") >= 0:
      g_server_exited = True
      break
  return

def start_server(scnt):
  global g_server_started, g_server_thread
  g_server_thread = threading.Thread(target=run_server_thread_func, args=(scnt,)) # always running
  g_server_thread.start()
  print("Waiting for the server to get started ...", flush=True)
  # wait until server fully started
  while not g_server_started:
    time.sleep(1)
  g_server_started = False
  return

def stop_server(scnt):
  global g_server_exited, g_server_thread
  status = scnt.exec_run(stateful_config.TRITON_SERVER_KILL_CMD)
  assert status[0] == 0
  print("Waiting for the server to exit ...", flush=True)
  while not g_server_exited:
    time.sleep(1)
  g_server_thread.join()
  g_server_exited = False
  return

def RunServer(root_dir):
  # create new container if not found
  scnt = stateful_utils.get_running_container(stateful_config.TRITON_SERVER_CONTAINER_NAME)
  if scnt is None:
    scnt = stateful_utils.create_container(stateful_config.TRITONSERVER_IMAGE, \
        cnt_name=stateful_config.TRITON_SERVER_CONTAINER_NAME, \
        with_gpus=True, ports=stateful_config.TRITON_PORTS, \
        shm_size=stateful_config.TRITON_SHM_SIZE, memlock=stateful_config.TRITON_MEMLOCK, \
        stack_size=stateful_config.TRITON_STACK, volumes=TRITON_VOLUMES)
    scnt.start()
  assert scnt != None
  scnt.reload()
  assert scnt.status == "running"
  status = scnt.exec_run(stateful_config.TRITON_SERVER_ONNXRT_CLEAN_CMD)
  # print(status[0], status[1].decode())
  assert status[0] == 0
  status = scnt.exec_run(stateful_config.TRITON_SERVER_COPY_BACKEND_CMD)
  # print(status[0], status[1].decode())
  assert status[0] == 0
  start_server(scnt)
  return scnt

def RunClient(root_dir):
  # create new container if not found
  ccnt = stateful_utils.get_running_container(stateful_config.TRITON_CLIENT_CONTAINER_NAME)
  if ccnt is None:
    ccnt = stateful_utils.create_container(stateful_config.TRITONCLIENT_IMAGE, \
        cnt_name=stateful_config.TRITON_CLIENT_CONTAINER_NAME, volumes=TRITON_VOLUMES)
    ccnt.start()
  assert ccnt != None
  ccnt.reload()
  assert ccnt.status == "running"
  status = ccnt.exec_run(stateful_config.TRITON_CLIENT_CMAKE_SETUP_CMD)
  # print(status[0], status[1].decode())
  assert status[0] == 0
  status = ccnt.exec_run(stateful_config.TRITON_CLIENT_CMAKE_CMD, workdir=stateful_config.TRITON_CLIENT_WORKDIR)
  print(status[0], status[1].decode())
  assert status[0] == 0
  status = ccnt.exec_run(stateful_config.TRITON_CLIENT_MAKE_CMD, workdir=stateful_config.TRITON_CLIENT_WORKDIR)
  # print(status[0], status[1].decode())
  assert status[0] == 0
  status = ccnt.exec_run(stateful_config.TRITON_CLIENT_RUN_CMD, workdir=stateful_config.TRITON_CLIENT_WORKDIR)
  print(status[1].decode())
  assert status[0] == 0
  return

def DoEverything(root_dir):
  err_happened = False
  # 0. setup the environment
  setup_env(root_dir)
  # 1. Build the backend
  build_backend.DoEverything(root_dir)
  # 2. Run the server
  scnt = RunServer(root_dir)
  # 3. Run the client
  try:
    RunClient(root_dir)
  except:
    err_happened = True
    print("Client error")
  time.sleep(2) # sleep for 2 seconds
  # 4. Stop the server
  stop_server(scnt)
  if err_happened:
    print("TEST FAILED!")
    exit(1)
  return

def main():
  root_dir = os.path.join(os.path.abspath(sys.path[0]), os.pardir)
  DoEverything(root_dir)
  print("TEST PASSED!")
  return

if __name__ == "__main__":
  main()