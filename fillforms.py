import argparse
import logging
import os
import sys

from src.pdf.builder import PDFItem, fill_national_form, prompt_rower_data, prompt_parent_data, prompt_extra_data, fill_image_form, \
    fill_xogade_form, fill_fegar_form, prompt_entity_data

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))


def _parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('sign_on', help='Date signed (DD/MM/YYYY')
    parser.add_argument('-t', '--type', help='Type of files to generate', nargs='*', default=['all'])
    parser.add_argument('-p', '--parent', action='store_true', default=False)
    parser.add_argument('--preset', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--entity', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--debug', action='store_true', default=False)
    return parser.parse_args()


def _fill_data(data: PDFItem, debug: bool) -> PDFItem:
    if debug:
        data.name = 'name'
        data.surname = 'surname'
        data.nif = '11753905P'
        data.gender = 'HOMBRE'
        data.birth = '23/11/2000'
        data.address = 'address'
        data.address_number = '15'
        data.postal_code = '15940'
        data.town = 'A POBRA DO CARAMIÑAL'
        data.state = 'A CORUÑA'
        data.category = 'CATEGORIA'

        data.parent_name = 'parent_name'
        data.parent_surname = 'parent_surname'
        data.parent_dni = '11753905P'
        return data

    data = prompt_rower_data(data)
    if args.parent:
        data = prompt_parent_data(data)
    if not args.entity:
        data = prompt_entity_data(data)
    if not args.preset:
        data = prompt_extra_data(data)
    return data


if __name__ == '__main__':
    args = _parse_arguments()
    logging.info(f'{os.path.basename(__file__)}:: args -> {args.__dict__}')

    values: PDFItem = PDFItem.preset(args.sign_on) if args.preset or args.debug else PDFItem()
    values = _fill_data(values, debug=args.debug)

    if 'national' in args.type or 'all' in args.type:
        fill_national_form(values, with_parent=args.parent)
    if 'image' in args.type or 'all' in args.type:
        fill_image_form(values, with_parent=args.parent)
    if 'fegar' in args.type or 'all' in args.type:
        fill_fegar_form(values, with_parent=args.parent)
    if args.parent and ('xogade' in args.type or 'all' in args.type):
        fill_xogade_form(values)
