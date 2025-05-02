import sys
import magic
import re
import unicodedata
import libs.DocXtoTXT as DXT
import libs.OldDoc as OD

def parse_cellosaurus(cello_txt_db) -> set:
    cl_names = set()
    with open(cello_txt_db, 'r') as cf:
        name = None
        for line in cf:
            name = line.strip().split("   ")[-1]
            if line.startswith("ID"):
                cl_names.add(name.strip())
            # and name ensures that an ID line precedes SY
            elif line.startswith("SY") and name:
                synonyms = line.strip().split('   ')[-1].split(";")
                for sy in synonyms:
                    cl_names.add(sy.strip())
        return cl_names

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
        search_match = re.search(r'(?:materials and methods|methods).*?results', man_text, re.DOTALL | re.IGNORECASE)
        man_text = search_match.group()
        return man_text
    elif file_type_info == "Microsoft Word 2007+":
        dxt = DXT.DocXtoTXT()
        return dxt.get_docx_txt(input_file)
    else:
        return ""

# return a list of all space positions in input string
def index_string(input_string) -> list:
    space_idx = []
    for idx, char in enumerate(input_string):
        if char == ' ':
            space_idx.append(idx)
    return  space_idx

def get_lines_containing_cells(man_lines, cl_names) -> list:
    matched_lines = set()
    for line in man_lines:
        if "cell" not in line.lower() and "culture" not in line.lower():
            continue
        #sort the cell lines list to match the longer cells first, to produce better samples

        for cl in sorted(cl_names, key=lambda x: len(x), reverse=True ):
            if f' {cl.lower()} ' in line.lower():
                print(f'{cl.lower()}:::{line.lower().find(cl.lower())}')
                first_part, second_part = line.lower().strip().split(cl.lower(), 1)
                first_part_5th_space = index_string(first_part)[-5]
                second_part_5th_space = index_string(second_part)[5]
                matched_lines.add(f'{first_part[first_part_5th_space:]}{cl}{second_part[:second_part_5th_space]}')
                break
    return list(matched_lines)


def main(argv):
    man_text = get_text_fromdoc(argv[1])
    man_lines = man_text.strip().splitlines()
    print(f'Lines selected:{len(man_lines)}')
    cl_names = parse_cellosaurus(argv[2])
    matched_lines = get_lines_containing_cells( man_lines, cl_names)
    for m_line in matched_lines:
        print(f'Matched Line:{m_line}')


if __name__ == "__main__":
    main(sys.argv)