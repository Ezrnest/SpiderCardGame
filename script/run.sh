#!/bin/bash

# 帮助信息：显示可用队列
show_usage() {
  echo "Usage:"
  echo "  $0 <python_script> [partition] [python_args...]"
  echo "  $0 -m <python_module> [partition] [python_args...]"
  echo "Partitions: amd_256 (default), amd_512, amd_1T, amd_2T, amd_test, amd_16core, amd_fast"
  exit 1
}

# 检查是否至少提供了 1 个参数
if [ $# -lt 1 ]; then
  show_usage
fi

# 支持两种调用：
# 1) run.sh script.py amd_512 --arg1 v1
# 2) run.sh script.py --arg1 v1
# 3) run.sh -m pkg.module amd_512 --arg1 v1
# 4) run.sh -m pkg.module --arg1 v1
known_partitions=("amd_256" "amd_512" "amd_1T" "amd_2T" "amd_test" "amd_16core" "amd_fast")
partition="amd_256"
run_mode="script"
target=""
arg_start=2

if [ "$1" == "-m" ]; then
  if [ $# -lt 2 ]; then
    show_usage
  fi
  run_mode="module"
  target="$2"
  arg_start=3
  if [ $# -ge 3 ]; then
    for p in "${known_partitions[@]}"; do
      if [ "$3" == "$p" ]; then
        partition="$3"
        arg_start=4
        break
      fi
    done
  fi
else
  run_mode="script"
  target="$1"
  arg_start=2
  if [ $# -ge 2 ]; then
    for p in "${known_partitions[@]}"; do
      if [ "$2" == "$p" ]; then
        partition="$2"
        arg_start=3
        break
      fi
    done
  fi
fi

pyargs=("${@:arg_start}")
pyargs_escaped=$(printf '%q ' "${pyargs[@]}")

# 根据队列自动设置核数 (ntasks)
# 默认 64 核，如果是 amd_16core 则强制设为 16 核
ntasks=64
if [ "$partition" == "amd_16core" ]; then
  ntasks=16
fi

# 生成任务名称
if [ "$run_mode" == "module" ]; then
  jobname=${target//./_}
else
  script_name=$(basename "$target")
  jobname=${script_name%.*}
fi

# 确保输出目录存在
mkdir -p out

echo "Submitting job: $jobname to Partition: $partition with $ntasks cores..."

target_escaped=$(printf '%q' "$target")
if [ "$run_mode" == "module" ]; then
  pycmd="~/.conda/envs/py313/bin/python -m $target_escaped $pyargs_escaped"
else
  pycmd="~/.conda/envs/py313/bin/python $target_escaped $pyargs_escaped"
fi

# 提交 sbatch 任务
sbatch <<EOT
#!/bin/bash
#SBATCH --job-name=$jobname
#SBATCH -p $partition
#SBATCH -N 1
#SBATCH --ntasks=$ntasks
#SBATCH -o out/%j.out

# 加载环境
source /public4/soft/modules/module.sh
module load miniforge
source /public4/soft/miniforge/24.11/bin/activate py313
export PYTHONUNBUFFERED=1

# 运行 Python 脚本
$pycmd
EOT
