from cutout.service.tasks_test_celery import ping

if __name__ == "__main__":
    result = ping.delay(42)
    print("Task submitted, waiting result...")
    print(result.get(timeout=10))
