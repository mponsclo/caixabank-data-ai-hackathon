import pandas as pd

# Load CSV files into pandas DataFrames
users_data = pd.read_csv("./data/raw/users_data.csv")

# Cast columns to appropriate data types
users_data["current_age"] = users_data["current_age"].astype(int)
users_data["retirement_age"] = users_data["retirement_age"].astype(int)
users_data["credit_score"] = users_data["credit_score"].astype(int)
users_data["num_credit_cards"] = users_data["num_credit_cards"].astype(int)
users_data["per_capita_income"] = users_data["per_capita_income"].replace("[\$,]", "", regex=True).astype(float)
users_data["yearly_income"] = users_data["yearly_income"].replace("[\$,]", "", regex=True).astype(float)
users_data["total_debt"] = users_data["total_debt"].replace("[\$,]", "", regex=True).astype(float)
# Create a new column 'birth_date' based on 'birth_year' and 'birth_month'
users_data["birth_date"] = pd.to_datetime(
    users_data["birth_year"].astype(str) + "-" + users_data["birth_month"].astype(str) + "-01"
)

cards_data = pd.read_csv("./data/raw/cards_data.csv")
# Cast columns to appropriate data types
cards_data["card_number"] = cards_data["card_number"].astype(int)
cards_data["cvv"] = cards_data["cvv"].astype(int)
cards_data["has_chip"] = cards_data["has_chip"].apply(lambda x: True if x == "YES" else False)
cards_data["num_cards_issued"] = cards_data["num_cards_issued"].astype(int)
cards_data["credit_limit"] = cards_data["credit_limit"].replace("[\$,]", "", regex=True).astype(float)
cards_data["card_on_dark_web"] = cards_data["card_on_dark_web"].apply(lambda x: True if x == "Yes" else False)
# Extract 'expiry_month' and 'expiry_year' from 'expires' and create a new column 'expiry_date'
cards_data["expiry_month"] = cards_data["expires"].str.split("/").str[0]
cards_data["expiry_year"] = cards_data["expires"].str.split("/").str[1]
cards_data["expiry_date"] = pd.to_datetime(
    cards_data["expiry_year"].astype(str) + "-" + cards_data["expiry_month"].astype(str) + "-01"
)

transactions_data = pd.read_csv("./data/raw/transactions_data.csv")
# Cast columns to appropriate data types
transactions_data["amount"] = pd.to_numeric(transactions_data["amount"].replace("[\$,]", "", regex=True))
transactions_data["merchant_id"] = pd.to_numeric(transactions_data["merchant_id"], errors="coerce").astype("Int64")
transactions_data["errors"] = pd.to_numeric(transactions_data["errors"], errors="coerce").fillna(0).astype("Int64")
transactions_data["mcc"] = transactions_data["mcc"].astype(float).fillna(0)


# Define a function to preprocess and save the DataFrame
def preprocess_and_save(
    df: pd.DataFrame, df_name: str, duplicate_columns: list, outlier_columns: list, output_path: str
) -> None:
    """
    Preprocess the DataFrame by checking for duplicates, missing values, and outliers, then save it to a CSV file.

    Args:
      df (pd.DataFrame): The DataFrame to preprocess.
      df_name (str): The name of the DataFrame.
      duplicate_columns (list): List of columns to check for duplicates.
      outlier_columns (list): List of columns to check for outliers.
      output_path (str): The path to save the processed DataFrame.
    """

    def check_duplicates(df: pd.DataFrame, columns: list) -> None:
        """
        Check for duplicate rows in the DataFrame based on specified columns and remove them.

        Args:
          df (pd.DataFrame): The DataFrame to check for duplicates.
          columns (list): List of columns to check for duplicates.
        """
        duplicates = df.duplicated(subset=columns)
        if duplicates.any():
            print(f"Found {duplicates.sum()} duplicate rows based on columns {columns}")
            df.drop_duplicates(subset=columns, inplace=True)
            print("Duplicates have been removed")
        else:
            print("No duplicates found")

    def check_missing_values(df: pd.DataFrame) -> None:
        """
        Check for missing values in the DataFrame and print the count of missing values per column.

        Args:
          df (pd.DataFrame): The DataFrame to check for missing values.
        """
        missing_values = df.isnull().sum()
        if missing_values.any():
            print(f"Missing values found: {len(missing_values[missing_values > 0])}")
            print(missing_values[missing_values > 0])
        else:
            print("No missing values found")

    def check_outliers(df: pd.DataFrame, columns: list) -> None:
        """
        Check for outliers in the specified numeric columns of the DataFrame and print the outliers.

        Args:
          df (pd.DataFrame): The DataFrame to check for outliers.
          columns (list): List of columns to check for outliers.
        """
        for column in columns:
            if pd.api.types.is_numeric_dtype(df[column]):
                Q1 = df[column].quantile(0.25)
                Q3 = df[column].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 3 * IQR
                upper_bound = Q3 + 3 * IQR
                outliers = df[(df[column] < lower_bound) | (df[column] > upper_bound)]
                if not outliers.empty:
                    print(f"Outliers detected in column {column}: {len(outliers)}")
                    print(outliers)
                else:
                    print(f"No outliers detected in column {column}")
            else:
                print(f"Column {column} is not numeric and will be skipped for outlier detection")

    # Perform data checks
    check_duplicates(df, duplicate_columns)
    check_missing_values(df)
    check_outliers(df, outlier_columns)

    # Save the final DataFrame to a CSV file
    df.to_csv(output_path, index=False)
    print(f"DataFrame {df_name} has been saved to {output_path}")


# Example usage
preprocess_and_save(
    users_data, "users_data", ["id"], ["current_age", "yearly_income"], "./data/processed/users_data_processed.csv"
)
preprocess_and_save(
    cards_data, "cards_data", ["id", "client_id"], ["credit_limit"], "./data/processed/cards_data_processed.csv"
)
preprocess_and_save(
    transactions_data,
    "transactions_data",
    ["id", "client_id", "card_id"],
    ["amount"],
    "./data/processed/transactions_data_processed.csv",
)
