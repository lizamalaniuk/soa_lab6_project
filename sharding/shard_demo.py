import redis

SHARDS = {
    1: redis.Redis(host="redis_shard1", port=6379, decode_responses=True),
    2: redis.Redis(host="redis_shard2", port=6379, decode_responses=True),
}


def get_shard(homework_id: int) -> int:
    """Determine shard by homework ID."""
    return 1 if homework_id % 2 else 2


def save_homework(homework_id: int) -> None:
    shard_id = get_shard(homework_id)
    key = f"lab6:python:{homework_id}"
    value = f"Homework {homework_id}"

    SHARDS[shard_id].set(key, value)
    print(f"{key} -> Shard {shard_id}")


def main():
    for homework_id in range(1, 11):
        save_homework(homework_id)

    print("\nShard distribution:")
    for shard_id, client in SHARDS.items():
        keys = sorted(client.scan_iter("lab6:python:*"))
        print(f"Shard {shard_id}: {len(keys)} keys")


if __name__ == "__main__":
    main()
