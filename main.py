from src.teamid import process_batch

RENTAL_CODES = [
    "BMYR5TU6TP",
]
POKEPASTE_RETRY_INTERVAL_SECONDS = 3
# FORCE_UPDATE_MODELS = False
FORCE_UPDATE_MODELS = True


def main():
    process_batch(
        RENTAL_CODES,
        pokepaste_retry_interval_seconds=POKEPASTE_RETRY_INTERVAL_SECONDS,
        force_update_models=FORCE_UPDATE_MODELS,
    )


if __name__ == "__main__":
    main()
