import requests
import time
import pandas as pd

def fetch_with_retry(url: str, retries: int = 3, delay: int = 5) -> dict:
    """
    Fetch data from the given URL with retries in case of failure.

    Args:
        url (str): The URL to fetch data from.
        retries (int): The number of retry attempts. Default is 3.
        delay (int): The delay between retries in seconds. Default is 5.

    Returns:
        dict: The JSON response from the URL.

    Raises:
        Exception: If the data could not be fetched after the specified retries.
    """
    for i in range(retries):
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:  # Too Many Requests
            print(f"Rate limit exceeded. Retrying in {delay} seconds...")
            time.sleep(delay)
        else:
            response.raise_for_status()
    raise Exception("Failed to fetch data after multiple retries.")

def fetch_clients_data(url: str, client_id: str) -> dict:
    """
    Fetch client data for a given client ID.

    Args:
        client_id (str): The ID of the client to fetch data for.

    Returns:
        dict: The JSON response containing client data.

    Raises:
        Exception: If the data could not be fetched or if the data format is incorrect.
    """
    url = f"{url}?client_id={client_id}"
    data = fetch_with_retry(url)
    if 'client_id' in data and data['client_id'] is None:
        print("Received incorrect data format.")
    return data

def fetch_all_clients_data(url:str, client_ids: list[str], csv_name: str) -> pd.DataFrame:
    """
    Fetch data for all clients given a list of client IDs.

    Args:
        client_ids (list[str]): A list of client IDs to fetch data for.

    Returns:
        pd.DataFrame: A DataFrame containing the data for all clients.

    Raises:
        Exception: If the data could not be fetched for a client.
    """
    all_client_data = []

    for client_id in client_ids:
        try:
            data = fetch_clients_data(url, client_id)
            print(data)
            # Assuming the data is in the format provided in the user prompt
            client_data = {
                'client_id': data['client_id'],
                **data['values']
            }

            # Append the client data to the list
            all_client_data.append(client_data)
        except Exception as e:
            print(f"Failed to fetch data for client {client_id}: {e}")
            continue

    # Create a DataFrame from the list of client data
    df = pd.DataFrame(all_client_data)

    # Save the DataFrame to a CSV file
    df.to_csv(f'./data/raw/{csv_name}.csv', index=False)

if __name__ == "__main__":
    client_ids = [str(client) for client in range(1, 1000)]
    df = fetch_all_clients_data("https://faas-lon1-917a94a7.doserverless.co/api/v1/web/fn-a1f52b59-3551-477f-b8f3-de612fbf2769/default/cards-data", client_ids, 'card_data')