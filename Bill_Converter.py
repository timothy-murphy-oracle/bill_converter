from flask import Flask, render_template, request, send_file, after_this_request
import zipfile
import pdfplumber
import pandas as pd
import re
import fitz
import os
import webview
from collections import namedtuple


def load_zip(file):
        return send_file(file)

app = Flask(__name__)

#ui = FlaskUI(app, width = 500, height = 500)
window = webview.create_window('BVC Automation Tool', app, width=1100, height=900)

"""
app.config['TRAP_HTTP_EXCEPTIONS']=True
@app.errorhandler(Exception)
def http_error_handler(error):
    return render_template('home.html')
"""
    
@app.route("/")
def home():
    return render_template('home.html')

@app.route("/view_data")
def view_data():
    zipObj = zipfile.ZipFile('data_files/Data Files.zip', 'w') 
    zipObj.write('data_files/azure_compute_shapes.csv')
    zipObj.write('data_files/azure_map_table.csv')
    zipObj.write('data_files/file_aws_compute_shapes.csv')
    zipObj.write('data_files/file_aws_map_table.csv')
    zipObj.close() 
    dir1 = os.getcwd()
    dirPath2 = os.path.join(dir1,'data_files/Data Files.zip')
    return send_file(dirPath2)



#Regular Dollar Signs 
@app.route('/process_input', methods = ['POST', 'GET'])
def process_input():

    file = request.files['user_input']
    
    try:
        file.save(file.filename) 
        file_path = str(file.filename)
    except:
        return render_template('home.html')

    pdf=pdfplumber.open(file)

    size_max = int(len(pdf.pages)) - 1

    try:
        orig_dir1 = os.getcwd()
        orig_dirPath2 = os.path.join(orig_dir1,'Output.zip')
        os.remove(orig_dirPath2)
    except:
        print('Unable to Remove Zip File')

    list_of_lines = []
    index = 0
    while index <= size_max:
        table=pdf.pages[index].extract_text()
        for line in table.split('\n'):
            page_num = index + 1
            tuple = (page_num, index, line)
            list_of_lines.append(tuple)
        index = index + 1
        
        
    try:    
        for item in list_of_lines:
            if item[2] == 'Details':
                idx = list_of_lines.index(item)
                break
        list_of_lines = list_of_lines[idx + 1:]
    except:
        list_of_lines = list_of_lines


    list_data = []
    for x in list_of_lines:    
        line = x[2]
        index = x[1]
        page_num = x[0]
        sliced_dollars_value = line.rfind(' $')
        if sliced_dollars_value != -1:
            sliced_dollars = str(line[line.rfind(' $'):])
            Description = line.replace(sliced_dollars, "")
            
            unit_result = re.findall("\s\d", Description)
            

            
        sliced_negative_dollars_value = line.rfind(' -$')
        if sliced_negative_dollars_value != -1:
            sliced_dollars = str(line[line.rfind(' -$'):])
            Description = line.replace(sliced_dollars, "")
            
            unit_result = re.findall("\s\d", Description)
            
            
            
        if (sliced_dollars_value == -1) and (sliced_negative_dollars_value == -1):
            Description = line 
            sliced_dollars = ""
            unit = ""
            unit_result = []
            
            
            
        if int(len(unit_result)) > 0:
            last_number = (unit_result[len(unit_result) - 1])
            
            unit = str(Description[Description.rfind(last_number):])
            Description = Description.replace(unit, "")
                
        else:
            unit = "" 
            
        tuple = (index, page_num, Description, unit, sliced_dollars)
        list_data.append(tuple)
    scrapped_data = pd.DataFrame(list_data, columns =['Index', 'Page_Number', 'Description', 'Unit', 'Price']) 


    scrapped_data['Unit'] = scrapped_data['Unit'].str.extract('(\d+(?:,\d+)*(?:\.\d+)?)', expand=False)
    scrapped_data['Unit']= scrapped_data['Unit'].str.replace(',','')
    scrapped_data['Unit'] = scrapped_data['Unit'].astype(float)

    #Where Andrews code would go
    scrapped_data = pd.DataFrame(scrapped_data.fillna(0))
    scrapped_data = pd.DataFrame(scrapped_data[scrapped_data['Unit']!=0])

    df_3_aws_compute_shapes = pd.read_csv('data_files/file_aws_compute_shapes.csv')
    df_4_aws_compute_shapes_list = df_3_aws_compute_shapes["unique_id_aws_compute_shapes"]\
        .values.tolist()

    # Compress all rows into a single string and add a straight dash in between them to be read into the regular expression as an "OR" in between each row
    df_5_aws_compute_shapes_string = "|".join(df_4_aws_compute_shapes_list)

    #df_5_aws_compute_shapes_string
    #Replace everything from here
    unique_ids = pd.DataFrame(scrapped_data['Description']\
                            .str\
                            .findall(df_5_aws_compute_shapes_string)\
                            .transform(''.join))\
    .rename(columns = {"Description": "unique_id"})

    clean_df_bill = pd.concat([scrapped_data, pd.DataFrame(unique_ids)], axis = 1)
    df_1_prod_map_table = pd.read_csv('data_files/file_aws_map_table.csv')
    df_7_bill_compare = pd.DataFrame(pd.merge(clean_df_bill,
                df_1_prod_map_table,
                on ='unique_id',
                how ='left'))

    pd.set_option('display.max_columns', 0)
    df_7_bill_compare = df_7_bill_compare.rename(columns={'Description': 'aws_item_description', 'Unit': 'aws_product_quantity', 'Price': 'aws_cost'})


    df_8_bill_compare = pd.DataFrame(df_7_bill_compare.assign(
        cpu_conversion = lambda x: 
            x['aws_vcpu']/2,
        compute_ocpu_new_cost = lambda x: 
            x['cpu_conversion'] * x['aws_product_quantity'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['not_grav_proc_comp'],
        memory_new_cost = lambda x: 
            (x['aws_memory_gib'] * 1.07374) * x['aws_product_quantity'] * x['oci_unit_price_memory'] * x['months'] * x['not_grav_proc_mem'],
        cost_of_windows_os = lambda x:
            x['oci_unit_price_compute_windows_os'] * x['cpu_conversion'] * x['aws_product_quantity'] * x['months'] * x['windows_os_y_n'],
        grav_proc_cost_comp = lambda x:
            (x['aws_product_quantity'] - x['aws_graviton_proc_free_tier_compute']) * x['cpu_conversion'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['aws_grav_proc'],
        grav_proc_cost_mem = lambda x:
            (x['aws_memory_gib'] * 1.07374) * (x['aws_product_quantity'] - x['aws_graviton_proc_free_tier_memory']) * x['oci_unit_price_memory'] * x['months'] * x['aws_grav_proc'],
        block_vol_stor_cost = lambda x:
            ((x['aws_product_quantity'] * x['oci_unit_price_block_vol'] * x['months']) + (x['oci_unit_price_block_vol_perf'] * x['months'] * (x['aws_product_quantity'] * x['block_vol_vpu_perf']))),
        obj_stor_cost = lambda x:
            (x['aws_product_quantity'] - 10) * x['months'] * x['oci_unit_price_obj_stor'],
        queue_cost = lambda x:
            ((x['aws_product_quantity'] - 1000000)/1000000) * x['oci_unit_price_queue'] * x['months'],
        api_gateway_cost = lambda x:
            (x['aws_product_quantity']/1000000) * x['oci_unit_price_api_gateway'] * x['months'],
        obj_stor_req_cost = lambda x:
            ((x['aws_product_quantity'] - 50000)/10000) * x['oci_obj_stor_req_unit_price'] * x['months'], 
        archive_stor_cost = lambda x:
            (x['aws_product_quantity'] - 10) * x['oci_archive_stor_unit_price'] * x['months'],
        logging_stor_cost = lambda x:
            (x['aws_product_quantity'] - 10) * x['oci_logging_stor_unit_price'] * x['months'],
        data_transfer_cost = lambda x:    
            (x['aws_product_quantity'] - 10000) * x['oci_datatransfer_unit_price'] * x['months'],
        kms_vault_cost = lambda x:
            (x['aws_product_quantity'] - 20) * x['oci_kms_vault_unit_price'] * x['months']))
            
    # Replace negative numbers with zero

    df_9_bill_compare = df_8_bill_compare._get_numeric_data()
    df_9_bill_compare[df_9_bill_compare < 0] = 0

    # Add a new column to calculate the total cost of OCI

    df_10_bill_compare = pd.DataFrame(df_8_bill_compare.assign(
        total_cost_oci = lambda x:
            ((x['compute_ocpu_new_cost'] + x['memory_new_cost'] + x['cost_of_windows_os'] + x['grav_proc_cost_comp'] + x['grav_proc_cost_mem']) * x['reserved_instance_discount']) + x['block_vol_stor_cost'] + x['obj_stor_cost'] + x['api_gateway_cost'] + x['queue_cost'] + x['obj_stor_req_cost'] + x['archive_stor_cost'] + x['logging_stor_cost'] + x['data_transfer_cost'] + x['kms_vault_cost']))

    df_10_bill_compare = df_10_bill_compare[~df_10_bill_compare['aws_product_quantity'].isna()]

    doc = fitz.open(file.filename)
    length_of_doc = int(len(doc)) - 1
    index = 0
    while index <= length_of_doc:
        page = doc.load_page(index)
        scraped_page = df_10_bill_compare.loc[df_10_bill_compare['Index'] == index]
        scraped_lines = scraped_page['aws_item_description'].tolist()
        for description in scraped_lines:
            text = str(description)
            text = text.rstrip('-')
            text_instances = page.search_for(text)
            for inst in text_instances:
                highlight = page.add_highlight_annot(inst)
                highlight.update()
        index = index + 1
        
    ### OUTPUT

    #Create the output files and put them into a zip file to download
    doc.save("Submitted PDF - Output.pdf", garbage=4, deflate=True, clean=True)
    doc.close()
    df_10_bill_compare.to_excel('Submitted PDF - Output.xlsx')
    zipObj = zipfile.ZipFile('Output.zip', 'w') 
    zipObj.write('Submitted PDF - Output.pdf')
    zipObj.write('Submitted PDF - Output.xlsx')
    zipObj.close() 
    dir1 = os.getcwd()
    dirPath2 = os.path.join(dir1,'Output.zip')

    try:
        os.remove('Submitted PDF - Output.xlsx')
        os.remove('Submitted PDF - Output.pdf')
        os.remove(file_path)
    except:
        print('Unable to Remove Files')

    load_zip(dirPath2)
    return render_template('output.html')


@app.route('/process_input_usd', methods = ['POST'])
def process_input_usd():
    
    file2 = request.files['user_input']
    
    try:
        file2.save(file2.filename) 
        file_path2 = str(file2.filename)
    except:
        return render_template('home.html')

    pdf=pdfplumber.open(file2)

    size_max = int(len(pdf.pages)) - 1

    try:
        orig_dir1 = os.getcwd()
        orig_dirPath2 = os.path.join(orig_dir1,'Output.zip')
        os.remove(orig_dirPath2)
    except:
        print('Unable to Remove Zip File')
    list_of_lines = []
    index = 0
    while index <= size_max:
        table=pdf.pages[index].extract_text()
        for line in table.split('\n'):
            page_num = index + 1
            tuple = (page_num, index, line)
            list_of_lines.append(tuple)
        index = index + 1
        
        
    try:   
        for item in list_of_lines:
            if item[2] == 'Charges by service':
                idx = list_of_lines.index(item)
                break
        list_of_lines = list_of_lines[idx + 1:]
    except:
        list_of_lines = list_of_lines


    list_data = []
    for x in list_of_lines: 
        line = x[2]
        index = x[1]
        page_num = x[0]
        sliced_dollars_value = line.rfind(' USD')
        if sliced_dollars_value != -1:
            sliced_dollars = str(line[line.rfind(' USD'):])
            Description = line.replace(sliced_dollars, "")
            
            sliced_dollars = re.sub(r'[^\d.]', '', sliced_dollars) 
            
            try:
                sliced_dollars = float(sliced_dollars)
            except:
                sliced_dollars = 0.0
            
            unit_result = re.findall("\s\d", Description)
            

            
        sliced_dollars_negative_value = line.rfind(' (USD')
        if sliced_dollars_negative_value != -1:
            sliced_dollars = str(line[line.rfind(' (USD'):])
            Description = line.replace(sliced_dollars, "")
            
            sliced_dollars = re.sub(r'[^\d.]', '', sliced_dollars) 
            sliced_dollars = -abs(float(sliced_dollars))

            
            unit_result = re.findall("\s\d", Description)
            
            
            
        if (sliced_dollars_value == -1) and (sliced_dollars_negative_value == -1):
            Description = line 
            sliced_dollars = 0
            unit = ""
            unit_result = []
            
            
            
        if int(len(unit_result)) > 0:
            last_number = (unit_result[len(unit_result) - 1])
            
            unit = str(Description[Description.rfind(last_number):])
            Description = Description.replace(unit, "")
                
        else:
            unit = "" 
            
        tuple = (index, page_num, Description, unit, sliced_dollars)
        list_data.append(tuple)
    scrapped_data = pd.DataFrame(list_data, columns =['Index', 'Page_Number', 'Description', 'Unit', 'Price']) 


    scrapped_data['Unit'] = scrapped_data['Unit'].str.extract('(\d+(?:,\d+)*(?:\.\d+)?)', expand=False)
    scrapped_data['Unit']= scrapped_data['Unit'].str.replace(',','')
    scrapped_data['Unit'] = scrapped_data['Unit'].astype(float)

    #Where Andrews code would go
    scrapped_data = pd.DataFrame(scrapped_data[scrapped_data['Unit']!=""])

    df_3_aws_compute_shapes = pd.read_csv('data_files/file_aws_compute_shapes.csv')
    df_4_aws_compute_shapes_list = df_3_aws_compute_shapes["unique_id_aws_compute_shapes"]\
        .values.tolist()

    # Compress all rows into a single string and add a straight dash in between them to be read into the regular expression as an "OR" in between each row
    df_5_aws_compute_shapes_string = "|".join(df_4_aws_compute_shapes_list)

    #df_5_aws_compute_shapes_string
    #Replace everything from here
    unique_ids = pd.DataFrame(scrapped_data['Description']\
                            .str\
                            .findall(df_5_aws_compute_shapes_string)\
                            .transform(''.join))\
    .rename(columns = {"Description": "unique_id"})

    clean_df_bill = pd.concat([scrapped_data, pd.DataFrame(unique_ids)], axis = 1)
    df_1_prod_map_table = pd.read_csv('data_files/file_aws_map_table.csv')
    df_7_bill_compare = pd.DataFrame(pd.merge(clean_df_bill,
                df_1_prod_map_table,
                on ='unique_id',
                how ='left'))

    pd.set_option('display.max_columns', 0)
    df_7_bill_compare = df_7_bill_compare.rename(columns={'Description': 'aws_item_description', 'Unit': 'aws_product_quantity', 'Price': 'aws_cost'})


    df_8_bill_compare = pd.DataFrame(df_7_bill_compare.assign(
        cpu_conversion = lambda x: 
            x['aws_vcpu']/2,
        compute_ocpu_new_cost = lambda x: 
            x['cpu_conversion'] * x['aws_product_quantity'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['not_grav_proc_comp'],
        memory_new_cost = lambda x: 
            (x['aws_memory_gib'] * 1.07374) * x['aws_product_quantity'] * x['oci_unit_price_memory'] * x['months'] * x['not_grav_proc_mem'],
        cost_of_windows_os = lambda x:
            x['oci_unit_price_compute_windows_os'] * x['cpu_conversion'] * x['aws_product_quantity'] * x['months'] * x['windows_os_y_n'],
        grav_proc_cost_comp = lambda x:
            (x['aws_product_quantity'] - x['aws_graviton_proc_free_tier_compute']) * x['cpu_conversion'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['aws_grav_proc'],
        grav_proc_cost_mem = lambda x:
            (x['aws_memory_gib'] * 1.07374) * (x['aws_product_quantity'] - x['aws_graviton_proc_free_tier_memory']) * x['oci_unit_price_memory'] * x['months'] * x['aws_grav_proc'],
        block_vol_stor_cost = lambda x:
            ((x['aws_product_quantity'] * x['oci_unit_price_block_vol'] * x['months']) + (x['oci_unit_price_block_vol_perf'] * x['months'] * (x['aws_product_quantity'] * x['block_vol_vpu_perf']))),
        obj_stor_cost = lambda x:
            (x['aws_product_quantity'] - 10) * x['months'] * x['oci_unit_price_obj_stor'],
        queue_cost = lambda x:
            ((x['aws_product_quantity'] - 1000000)/1000000) * x['oci_unit_price_queue'] * x['months'],
        api_gateway_cost = lambda x:
            (x['aws_product_quantity']/1000000) * x['oci_unit_price_api_gateway'] * x['months'],
        obj_stor_req_cost = lambda x:
            ((x['aws_product_quantity'] - 50000)/10000) * x['oci_obj_stor_req_unit_price'] * x['months'], 
        archive_stor_cost = lambda x:
            (x['aws_product_quantity'] - 10) * x['oci_archive_stor_unit_price'] * x['months'],
        logging_stor_cost = lambda x:
            (x['aws_product_quantity'] - 10) * x['oci_logging_stor_unit_price'] * x['months'],
        data_transfer_cost = lambda x:    
            (x['aws_product_quantity'] - 10000) * x['oci_datatransfer_unit_price'] * x['months'],
        kms_vault_cost = lambda x:
            (x['aws_product_quantity'] - 20) * x['oci_kms_vault_unit_price'] * x['months']))
            
    # Replace negative numbers with zero

    df_9_bill_compare = df_8_bill_compare._get_numeric_data()
    df_9_bill_compare[df_9_bill_compare < 0] = 0

    # Add a new column to calculate the total cost of OCI

    df_10_bill_compare = pd.DataFrame(df_8_bill_compare.assign(
        total_cost_oci = lambda x:
            ((x['compute_ocpu_new_cost'] + x['memory_new_cost'] + x['cost_of_windows_os'] + x['grav_proc_cost_comp'] + x['grav_proc_cost_mem']) * x['reserved_instance_discount']) + x['block_vol_stor_cost'] + x['obj_stor_cost'] + x['api_gateway_cost'] + x['queue_cost'] + x['obj_stor_req_cost'] + x['archive_stor_cost'] + x['logging_stor_cost'] + x['data_transfer_cost'] + x['kms_vault_cost']))

    df_10_bill_compare = df_10_bill_compare[~df_10_bill_compare['aws_product_quantity'].isna()]

    doc = fitz.open(file_path2)
    length_of_doc = int(len(doc)) - 1
    index = 0
    while index <= length_of_doc:
        page = doc.load_page(index)
        scraped_page = df_10_bill_compare.loc[df_10_bill_compare['Index'] == index]
        scraped_lines = scraped_page['aws_item_description'].tolist()
        for description in scraped_lines:
            text = str(description)
            text = text.rstrip('-')
            text_instances = page.search_for(text)
            for inst in text_instances:
                highlight = page.add_highlight_annot(inst)
                highlight.update()
        index = index + 1
        
    ### OUTPUT

    #Create the output files and put them into a zip file to download
    doc.save("Submitted PDF - Output.pdf", garbage=4, deflate=True, clean=True)
    doc.close()
    df_10_bill_compare.to_excel('Submitted PDF - Output.xlsx')
    zipObj = zipfile.ZipFile('Output.zip', 'w') 
    zipObj.write('Submitted PDF - Output.pdf')
    zipObj.write('Submitted PDF - Output.xlsx')
    zipObj.close() 
    dir1 = os.getcwd()
    dirPath2 = os.path.join(dir1,'Output.zip')

    try:
        os.remove('Submitted PDF - Output.xlsx')
        os.remove('Submitted PDF - Output.pdf')
        os.remove(file_path2)
    except:
        print('Unable to Remove Files')
    
    load_zip(dirPath2)
    return render_template('output.html')





@app.route('/process_input_aws_csv', methods = ['POST'])
def process_input_aws_csv():
    file3 = request.files['user_input_csv']

    file3.save(file3.filename) 
    file_path3 = str(file3.filename)
    df_2_bill = pd.read_csv(file_path3)

    
    try:
        orig_dir1 = os.getcwd()
        orig_dirPath2 = os.path.join(orig_dir1,'AWS CSV Output.csv')
        os.remove(orig_dirPath2)
    except:
        print('Unable to remove output')


    #Start Process
    df_1_prod_map_table = pd.read_csv('data_files/file_aws_map_table.csv')
    
    df_3_aws_compute_shapes = pd.read_csv('data_files/file_aws_compute_shapes.csv')

    df_4_aws_compute_shapes_list = df_3_aws_compute_shapes["unique_id_aws_compute_shapes"]\
        .values.tolist()
    df_5_aws_compute_shapes_string = "|".join(df_4_aws_compute_shapes_list)

    unique_ids = pd.DataFrame(df_2_bill['aws_item_description']\
                          .str\
                          .findall(df_5_aws_compute_shapes_string)\
                          .transform(''.join))\
    .rename(columns = {"aws_item_description": "unique_id"})

    clean_df_bill = pd.concat([df_2_bill, pd.DataFrame(unique_ids)], axis = 1)

    df_7_bill_compare = pd.DataFrame(pd.merge(clean_df_bill,
               df_1_prod_map_table,
               on ='unique_id',
               how ='left'))

    pd.set_option('display.max_columns', 0)
    df_8_bill_compare = pd.DataFrame(df_7_bill_compare.assign(
    cpu_conversion = lambda x: 
        x['aws_vcpu']/2,
    compute_ocpu_new_cost = lambda x: 
        x['cpu_conversion'] * x['aws_product_quantity'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['not_grav_proc_comp'],
    memory_new_cost = lambda x: 
        (x['aws_memory_gib'] * 1.07374) * x['aws_product_quantity'] * x['oci_unit_price_memory'] * x['months'] * x['not_grav_proc_mem'],
    cost_of_windows_os = lambda x:
        x['oci_unit_price_compute_windows_os'] * x['cpu_conversion'] * x['aws_product_quantity'] * x['months'] * x['windows_os_y_n'],
    grav_proc_cost_comp = lambda x:
        (x['aws_product_quantity'] - x['aws_graviton_proc_free_tier_compute']) * x['cpu_conversion'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['aws_grav_proc'],
    grav_proc_cost_mem = lambda x:
        (x['aws_memory_gib'] * 1.07374) * (x['aws_product_quantity'] - x['aws_graviton_proc_free_tier_memory']) * x['oci_unit_price_memory'] * x['months'] * x['aws_grav_proc'],
    block_vol_stor_cost = lambda x:
        ((x['aws_product_quantity'] * x['oci_unit_price_block_vol'] * x['months']) + (x['oci_unit_price_block_vol_perf'] * x['months'] * (x['aws_product_quantity'] * x['block_vol_vpu_perf']))),
    obj_stor_cost = lambda x:
        (x['aws_product_quantity'] - 10) * x['months'] * x['oci_unit_price_obj_stor'],
    queue_cost = lambda x:
        ((x['aws_product_quantity'] - 1000000)/1000000) * x['oci_unit_price_queue'] * x['months'],
    api_gateway_cost = lambda x:
        (x['aws_product_quantity']/1000000) * x['oci_unit_price_api_gateway'] * x['months'],
    obj_stor_req_cost = lambda x:
        ((x['aws_product_quantity'] - 50000)/10000) * x['oci_obj_stor_req_unit_price'] * x['months'], 
    archive_stor_cost = lambda x:
        (x['aws_product_quantity'] - 10) * x['oci_archive_stor_unit_price'] * x['months'],
    logging_stor_cost = lambda x:
        (x['aws_product_quantity'] - 10) * x['oci_logging_stor_unit_price'] * x['months'],
    data_transfer_cost = lambda x:    
        (x['aws_product_quantity'] - 10000) * x['oci_datatransfer_unit_price'] * x['months'],
    kms_vault_cost = lambda x:
        (x['aws_product_quantity'] - 20) * x['oci_kms_vault_unit_price'] * x['months']))
        
# Replace negative numbers with zero

    df_9_bill_compare = df_8_bill_compare._get_numeric_data()
    df_9_bill_compare[df_9_bill_compare < 0] = 0

# Add a new column to calculate the total cost of OCI

    df_10_bill_compare = pd.DataFrame(df_8_bill_compare.assign(
    total_cost_oci = lambda x:
        ((x['compute_ocpu_new_cost'] + x['memory_new_cost'] + x['cost_of_windows_os'] + x['grav_proc_cost_comp'] + x['grav_proc_cost_mem']) * x['reserved_instance_discount']) + x['block_vol_stor_cost'] + x['obj_stor_cost'] + x['api_gateway_cost'] + x['queue_cost'] + x['obj_stor_req_cost'] + x['archive_stor_cost'] + x['logging_stor_cost'] + x['data_transfer_cost'] + x['kms_vault_cost']))

    




    ### OUTPUT

    #Create the output files and put them into a zip file to download
    df_10_bill_compare.to_csv('AWS CSV Output.csv', index=False, na_rep='Unkown')
    dir1 = os.getcwd()
    dirPath2 = os.path.join(dir1,'AWS CSV Output.csv')

    try:
        os.remove(file_path3)
    except:
        print('Unable to Remove Files')
    
    load_zip(dirPath2)
    return render_template('output.html')



@app.route('/process_input_azure_csv', methods = ['POST'])
def process_input_azure_csv():  
    file4 = request.files['user_input_csv']
    file4.save(file4.filename) 
    file_path4 = str(file4.filename)
    df_2_bill = pd.read_csv(file_path4)


    try:
        orig_dir1 = os.getcwd()
        orig_dirPath2 = os.path.join(orig_dir1,'Azure CSV Output.csv')
        os.remove(orig_dirPath2)
    except:
        print('Unable to remove output')    



    df_1_prod_map_table = pd.read_csv('data_files/azure_map_table.csv')
    df_3_azure_compute_shapes = pd.read_csv('data_files/azure_compute_shapes.csv')

    df_2_bill['quantity'] = df_2_bill['quantity'].astype(float)
    df_4_azure_compute_shapes_list = df_3_azure_compute_shapes["unique_id_azure_compute_shapes"]\
    .values.tolist()
    df_5_azure_compute_shapes_string = "|".join(df_4_azure_compute_shapes_list)
    unique_ids = pd.DataFrame(df_2_bill['product']\
                          .str\
                          .findall(df_5_azure_compute_shapes_string)\
                          .transform(''.join))\
    .rename(columns = {"product": "unique_id"})

    clean_df_bill = pd.concat([df_2_bill, pd.DataFrame(unique_ids)], axis = 1)
    df_7_bill_compare = pd.DataFrame(pd.merge(clean_df_bill,
               df_1_prod_map_table,
               on ='unique_id',
               how ='left'))
    pd.set_option('display.max_columns', 0)


    df_8_bill_compare = pd.DataFrame(df_7_bill_compare.assign(
    cpu_conversion = lambda x: 
        x['azure_vcpu']/2,
    compute_ocpu_new_cost = lambda x: 
        x['cpu_conversion'] * x['quantity'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['not_a1_oci_shape_comp'],
    memory_new_cost = lambda x: 
        x['azure_memory_gb'] * x['quantity'] * x['oci_unit_price_memory'] * x['months'] * x['not_a1_oci_shape_mem'],
    cost_of_windows_os = lambda x:
        x['oci_unit_price_compute_windows_os'] * x['cpu_conversion'] * x['quantity'] * x['months'] * x['windows_os_y_n'],
    a1_shape_cost_comp = lambda x:
        (x['quantity'] - x['a1_oci_shape_free_tier_compute']) * x['cpu_conversion'] * x['oci_unit_price_ocpu'] * x['months'] * x['baseline_capacity'] * x['a1_oci_shape'],
    a1_shape_cost_mem = lambda x:
        (x['quantity'] - x['a1_oci_shape_free_tier_memory']) * x['azure_memory_gb'] * x['oci_unit_price_memory'] * x['months'] * x['a1_oci_shape'],
    load_balancer_cost= lambda x:
        (((x['quantity'] * 100)/744) * x['months'] * x['oci_unit_price_load_balancer'] * 744) + (x['oci_unit_price_load_bal_bandwidth'] * (((x['quantity'] * 100)/744) * 10) * x['months'] * 744),
    cloud_guard = lambda x: 
        x['quantity'] * 0))                                                                                                                  
                                                                                                                  
# Replace negative numbers with zero

    df_9_bill_compare = df_8_bill_compare._get_numeric_data()
    df_9_bill_compare[df_9_bill_compare < 0] = 0

# Add a new column to calculate the total cost of OCI

    df_10_bill_compare = pd.DataFrame(df_8_bill_compare.assign(
        total_cost_oci = lambda x:
            x['compute_ocpu_new_cost'] + x['memory_new_cost'] + x['cost_of_windows_os'] + x['a1_shape_cost_comp'] + x['a1_shape_cost_mem'] + x['load_balancer_cost'] + x['cloud_guard']))

    
    
    
    #Create the output files and put them into a zip file to download
    df_10_bill_compare.to_csv('Azure CSV Output.csv', index=False, na_rep='Unkown') 
    dir1 = os.getcwd()
    dirPath2 = os.path.join(dir1,'Azure CSV Output.csv')
    try:
        os.remove(file_path4)
    except:
        print('Unable to Remove Files')
    
    load_zip(dirPath2)
    return render_template('output.html')



def application(environ, start_response):
    return app(environ, start_response)

if __name__ == "__main__":
    webview.start(private_mode=False)