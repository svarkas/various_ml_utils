import collect_training_data
import sys

def main(args):
    if collect_training_data.filter_cells(args[1]):
        print(f'{args[1]}: is cell')
    else:
        print(f'{args[1]}: is not a cell')

if __name__ == "__main__":
    main(sys.argv)

