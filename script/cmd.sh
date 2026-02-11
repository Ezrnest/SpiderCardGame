./run.sh -m solver.seed_pool_builder \
  --suits 4 \
  --start-seed 1 \
  --count 50000 \
  --workers 64 \
  --max-seconds 20 \
  --max-nodes 2000000 \
  --max-frontier 1000000



python -m solver.seed_pool_builder \
  --suits 1 \
  --count 50 \
  --workers 8 \
  --max-seconds 5 \
  --max-nodes 2000000 \
  --max-frontier 1000000



python -m solver.seed_pool_builder \
  --suits 4 \
  --count 50 \
  --workers 8 \
  --max-seconds 10 \
  --max-nodes 2000000 \
  --max-frontier 1000000 \
  --start-seed 1