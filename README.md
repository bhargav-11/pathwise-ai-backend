# pathwise-ai-backend


## Steps
 - Login to vm.
 - go in to 'Langchain_pathwise' folder.
 - run this command to activate virtual environment "source myenv/bin/activate".
 - run the script using "python3 poc-lang.py".
 - provide the google drive folder id.
 - Give consent if files in the folder changed and you want to reembed.
 - start chatting with the documents in the drive.


## Instructions
 - If the embeddings for the folder does not exists then it wont ask to reembed it and create embeddings.
 - If the embeddings for the folder exists, It will ask if the user wants to reembed.
 - If the files in the folder changed. The user can reembed.