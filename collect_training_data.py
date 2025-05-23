import random
import sys
import magic
import re
import unicodedata
import libs.DocXtoTXT as DXT
import libs.OldDoc as OD
import libs.Shell as SL
import libs.AmazonS3 as AS3
import libs.UseJournalDB as UDB
import config as CFG
import os
import json

'''
returns a list with all unique cell lines to lower case, 
do we want that or we need all cases ????
'''
def parse_cellosaurus(cello_txt_db) -> set:
    cl_names = set()
    with open(cello_txt_db, 'r') as cf:
        name = None
        for line in cf:
            name = line.strip().split("   ")[-1]
            if line.startswith("ID"):
                cl_names.add(name.strip().lower())
            elif line.startswith("SY"):
                synonyms = line.strip().split('   ')[-1].split(";")
                for sy in synonyms:
                    cl_names.add(sy.strip().lower())
        return list(set(cl_names))

def get_text_fromdoc(input_file) -> str:
    extension = input_file.split(".")[-1]
    file_type_info = magic.from_file(input_file)
    if "Composite Document File V2 Document" in file_type_info:
        od = OD.OldDoc()
        man_text = od.extractText(input_file)
        # man_text = unicodedata.normalize("NFKC", man_text)
        man_text = man_text.replace("\xa0", " ").replace("\u200b", "")
        man_text = man_text.replace("\r\n", "\n").replace("\r", "\n")
        man_text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", man_text)
    elif file_type_info == "Microsoft Word 2007+":
        dxt = DXT.DocXtoTXT()
        man_text = dxt.get_docx_txt(input_file)
    else:
        man_text = ""

    try:
        search_match = re.search(r'(?:materials and methods|methods).*?results', man_text, re.DOTALL | re.IGNORECASE)
        man_text = search_match.group()
    except AttributeError as e:
        man_text = ''
        print(f'ERROR:(get_text_fromdoc) failed to locate materials and Methods section in {input_file} with ERROR{e}.')

    return man_text

# return a list of all space positions in input string
def index_string(input_string) -> list:
    space_idx = []
    for idx, char in enumerate(input_string):
        if char == ' ':
            space_idx.append(idx)
    return  space_idx

def filter_cells(cl):

    patterns = ['[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{2,4}',
                '[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{2,4}',
                '[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{2,4}[-_ ./#]{1,2}[a-zA-Z0-9]{2,4}',
                '[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{2,4}[-_ ./#]{1,2}[a-zA-Z0-9]{2,4}[-_ ./#]{1,2}[a-zA-Z0-9]{2,4}',
                '[a-zA-Z]{2}[0-9]{2,4}',
                '[a-zA-Z0-9]{1,4}[-_ ./#]{1,2}[0-9]{1,4}',
                '[0-9]{1,4}[-_ ./#]{1,2}[a-zA-Z0-9]{1,4}']
    is_valid = False
    for pattern in patterns:
        if re.fullmatch(pattern,cl):
            is_valid = True
    return is_valid

def get_lines_containing_cells(man_lines, cl_names) -> list:
    matched_lines = []
    rand =  random.Random()
    for line in man_lines:
        if "cell" not in line.lower() and "culture" not in line.lower():
            continue
        #sort the cell lines list to match the longer cells first, to produce better samples

        # for cl in cl_names:
        for cl in sorted(cl_names, key=lambda x: len(x), reverse=True ):
            #if cl.lower() not in ['of', 'has', 'cancer', 'all', 'at', 'we', 'may']:
            if filter_cells(cl):
                random_pre_phrase_selector = rand.randint(-7, -3)
                random_post_phrase_selector = rand.randint(3, 7)
                if f' {cl.lower()} ' in line.lower():
                    #print(f'{cl.lower()}:::{line.lower().find(cl.lower())}')
                    first_part, second_part = line.lower().strip().split(cl.lower(), 1)
                    try:
                        first_part_5th_space = index_string(first_part)[random_pre_phrase_selector]
                        second_part_5th_space = index_string(second_part)[random_post_phrase_selector]
                        matched_lines.append({cl:f'{first_part[first_part_5th_space:]}{cl}{second_part[:second_part_5th_space]}'})
                        # only the string with colour
                        #atched_lines.append(f'{first_part[first_part_5th_space:]}\033[31m{cl}\033[0m{second_part[:second_part_5th_space]}')
                        break
                    except IndexError as e:
                        continue
    return list(matched_lines)

def second_pass(matched_lines, cl_names) -> list:
    line_cells_pairs = []
    for mline in matched_lines:
        line = next(iter(mline.values()))
        cells_list = []
        contains_cells = False
        for cl in sorted(cl_names, key=lambda x: len(x), reverse=True):
            if filter_cells(cl):
                if f' {cl.lower()} ' in line.lower() or f' {cl.lower()},' in line.lower():
                    cells_list.append(cl)
                    contains_cells = True
        if contains_cells:
            line_cells_pairs.append({line:cells_list})
    return  line_cells_pairs

def get_remote_input_files(input_list):
    sl = SL.Shell()
    as3 = AS3.AmazonS3()
    udb = UDB.UseJournalDB()
    with open(input_list,'r') as f:
        for line in f:
            submission_id, full_filename = line.strip().split(':')
            filename = full_filename.strip().split('/')[-1]
            localfile = f'{submission_id}.{filename.strip().split('.')[-1]}'
            downloaded_list = os.listdir(CFG.working_dir)
            if f'{submission_id}.doc' in downloaded_list or f'{submission_id}.docx' in downloaded_list:
                print(f'{submission_id} is already here')
            else:
                if not sl.scp_get(f'{CFG.path_to_subs}/SUBMISSION_NO_{submission_id}/{filename}', f'{CFG.working_dir}/{localfile}'):
                     print(f'(get_remote_input_files) failed to get {submission_id} from prod, trying the S3 bucket...')
                     aws_filepath =  udb.get_manuscript(submission_id)
                     as3.get_file('prodportal', aws_filepath, f"{CFG.working_dir}/{submission_id}.{filename.strip().split('.')[-1]}")

def select_files_to_process() -> list :
    dir_content = os.listdir(CFG.working_dir)
    pattern = '[0-9]{6}[.]doc[x]*'
    files_to_process = []
    for file in dir_content:
        if re.match(pattern, file):
            files_to_process.append(file)
    return files_to_process

def tokenize_text(input_text) -> list:
    words = []
    words =  input_text.strip().split(' ')
    #print(words)
    return words

def cell_occurences(input_text, cell) -> list:
    cell_indexes = []
    start = 0
    while True:
        index = input_text.find(cell, start)
        if index == -1:
            break
        cell_indexes.append(index)
        start = index + 1
    return cell_indexes

def labelize(input_text, cells) -> list:
    line_tokens = tokenize_text(input_text)
    labels = ['O'] * len(line_tokens)
    for cell in cells:
       #print(f'{cell}:::{cell_start}:::{cell_end}')
        # locate all the occurences of the cell in line
        for cell_index in cell_occurences(input_text, cell):
            per_token_index = 1
            cell_start = cell_index
            cell_end = cell_index + len(cell)
            for i in range(0, len(line_tokens)):
                #print(per_token_index)
                '''
                for multipart cell lines like "0.5 alpha". the 0.5 cell part
                could be matched alone in another part of the line.
                to prevent this I calculate the  offset(START) and the offset+cell lenght (END)
                and I force the match to be within those boundaries, then I search the line's tokens
                in the cell not the cell in line
                '''
                if cell_start <= per_token_index <= cell_end:
                    if cell.lower().find(line_tokens[i].lower().strip('(),. ')) == 0:
                        labels[i] = 'B-CELL'
                    elif cell.lower().find(line_tokens[i].lower()) > 0:
                        labels[i] = 'I-CELL'
                per_token_index = per_token_index + len(line_tokens[i]) + 1

    return list(zip(line_tokens,labels))

def bertify(labeled_tokens) -> list:
    labels = []
    tokens = []
    for pair in labeled_tokens:
        tokens.append(pair[0])
        labels.append(pair[1])
    labels_tokens = [{'tokens':tokens}, {'labels':labels}]
    return labels_tokens

def main(argv):
    cl_names = parse_cellosaurus(argv[2])
    #get_remote_input_files(argv[1])

    #print(bertify(labelize("sciences. co the Human Lung adenocarcinoma cell line co nci-h1975 22 was purchased from", "co nci-h1975 22")))
    #print(bertify(labelize("scies. co the cell line co nci-h1975 22 was purchased from", "co nci-h1975 22")))
    files_to_process = select_files_to_process()
    for file in files_to_process:
        man_text = get_text_fromdoc(f'{CFG.working_dir}/{file}')
        #os.rename(f'{CFG.working_dir}/{file}', f'{CFG.working_dir}/processed/{file}')
        man_lines = man_text.strip().splitlines()
        matched_lines = get_lines_containing_cells(man_lines, cl_names)
        matched_lines_with_cells = second_pass(matched_lines,cl_names)
        for line_cell_dict in matched_lines_with_cells:
            line = next(iter(line_cell_dict.keys()))
            cells = next(iter(line_cell_dict.values()))
            with open(f'{CFG.working_dir}/train_data.jsonl', 'a', encoding='utf-8') as ft:
                ft.write(json.dumps(bertify(labelize(line, cells))))
                ft.write('\n')



if __name__ == "__main__":
    main(sys.argv)
