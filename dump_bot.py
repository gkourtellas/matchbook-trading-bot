import os

def combine_files():
    # Files to look for in the current directory and src/
    files_to_check = [
        'src/api_client.py',
        'src/strategy_one.py',
        'docs/STRATEGY.md',
        'docs/TROUBLESHOOTING.md',
        'logs/bot.log'
    ]
    
    output_file = 'bot_troubleshooting_dump.md'
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("# Matchbook Trading Bot - Source Code Dump\n\n")
        outfile.write("This file contains the core Python implementation and logs for troubleshooting.\n\n")
        
        for file_path in files_to_check:
            outfile.write(f"## File: {file_path}\n\n")
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                    
                    # Determine markdown code block language
                    lang = 'python' if file_path.endswith('.py') else 'markdown' if file_path.endswith('.md') else 'text'
                    
                    outfile.write(f"```{lang}\n")
                    outfile.write(content)
                    if not content.endswith('\n'):
                        outfile.write('\n')
                    outfile.write("```\n\n")
                except Exception as e:
                    outfile.write(f"*Error reading file: {str(e)}*\n\n")
            else:
                outfile.write("*File not found in this path.*\n\n")
                
    print(f"Successfully created {output_file}")

if __name__ == '__main__':
    combine_files()