from src.teamid import process_batch

RENTAL_CODES = [
"165QXUL6DU",
"HQEKBCH292",
"QGM0R1M6JR",
"F8R525FSSE",
"PTF1KG3JJL",
"JVNXYVG6AS",
"6AS3XFULSE",
]
POKEPASTE_RETRY_INTERVAL_SECONDS = 3
FORCE_UPDATE_MODELS = False
# FORCE_UPDATE_MODELS = True


def main():
    process_batch(
        RENTAL_CODES,
        pokepaste_retry_interval_seconds=POKEPASTE_RETRY_INTERVAL_SECONDS,
        force_update_models=FORCE_UPDATE_MODELS,
    )


if __name__ == "__main__":
    main()
