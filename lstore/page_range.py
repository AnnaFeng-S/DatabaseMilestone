from lstore.bt_page import Base_Page, Tail_Page
import time

SPECIAL_RID = (2**64)-1
RID_COLUMN = 0
BASE_PAGE_MAX_SIZE = 16
TAIL_BLOCK_SIZE = 64
PHYSICAL_PAGE_SIZE = 512

class Page_Range:
    def __init__(self, num_columns, brid, trid):
        self.base_page = []
        self.tail_page = []
        self.n_columns = num_columns
        self.next_bpage = 0
        self.next_tpage = 0
        self.next_brid = brid
        self.next_trid = trid
        self.trid_list = [trid]

    def has_capacity(self):
        if len(self.base_page) == BASE_PAGE_MAX_SIZE and not(self.base_page[15].has_capacity()):
            return False
        else:
            return True
    
    def tail_has_capacity(self):
        if (self.next_tpage != 0) and (len(self.tail_page) % TAIL_BLOCK_SIZE == 0) and not(self.tail_page[len(self.tail_page)-1].has_capacity()):
            return False
        else:
            return True

    def new_base_page(self):
        if len(self.base_page) < BASE_PAGE_MAX_SIZE:
            self.base_page.append(Base_Page(self.n_columns))
            self.next_bpage += 1
        else:
            return False
    
    def new_tail_page(self):
        self.tail_page.append(Tail_Page(self.n_columns))
        self.next_tpage += 1
        
    def more_tail_page(self, new_trid):
        self.next_trid = new_trid
        self.trid_list.append(new_trid)

    def getNextRID(self):
        self.next_brid += 1
        return (self.next_brid - 1)

    def getNextTRID(self):
        self.next_trid += 1
        return (self.next_trid - 1)
        
    def b_write(self, values):
        if (self.next_brid % PHYSICAL_PAGE_SIZE == 0):
            self.new_base_page()
        rid = self.getNextRID()
        self.base_page[-1].meta_data.write_RID(rid)
        self.base_page[-1].meta_data.write_SCHEMA(0)
        self.base_page[-1].meta_data.write_INDIRECTION(rid)
        self.base_page[-1].meta_data.write_TIMESTAMP(int(time.time()))
        for i in range(0, self.n_columns):
            self.base_page[-1].write_col(i, values[i])
        loc_info = [rid, self.next_bpage - 1, rid % PHYSICAL_PAGE_SIZE]
        return loc_info

    def t_locate(self, trid):
        page_block = 0
        for i in range(0, len(self.trid_list)):
            if trid - self.trid_list[i] < TAIL_BLOCK_SIZE*PHYSICAL_PAGE_SIZE:
                page_block = i
                break
        page_index = int((trid-self.trid_list[page_block]) / PHYSICAL_PAGE_SIZE) + TAIL_BLOCK_SIZE * page_block
        index = int((trid-self.trid_list[page_block]) % PHYSICAL_PAGE_SIZE)
        return [page_index, index]

    def b_read(self, page_index, index):
        record = []
        if self.base_page[page_index].meta_data.read_SCHEMA(index) == 0:
            for i in range(0, self.n_columns):
                record.append(self.b_read_col(page_index, index, i))
        else:
            new_loc = self.base_page[page_index].meta_data.read_INDIRECTION(index)
            [new_page_index, new_index] = self.t_locate(new_loc)
            for i in range(0, self.n_columns):
                record.append(self.t_read_col(new_page_index, new_index, i))
        return record
    
    def b_update(self, page_index, index, column, value):
        self.base_page[page_index].update(index, column, value)

    def t_update_col(self, page_index, index, column, value):
        self.tail_page[page_index].update(index, column, value)

    def b_read_col(self, page_index, index, column):
        return self.base_page[page_index].read(index, column)

    def t_read_col(self, page_index, index, column):
        return self.tail_page[page_index].read(index, column)

    def t_update(self, page_index, index, values):
        if ((self.next_trid-self.trid_list[-1]) % PHYSICAL_PAGE_SIZE == 0):
            self.new_tail_page()
        new_record = []
        base_rid = self.base_page[page_index].meta_data.read_RID(index)
        next_tid = self.getNextTRID()
        self.tail_page[-1].meta_data.write_TID(next_tid)
        self.tail_page[-1].meta_data.write_RID(base_rid)
        self.tail_page[-1].meta_data.write_TIMESTAMP(int(time.time()))
        if self.base_page[page_index].meta_data.read_SCHEMA(index) == 0:
            self.tail_page[-1].meta_data.write_INDIRECTION(base_rid)
            for i in range(0, self.n_columns):
                if values[i] == None:
                    new_record.append(self.b_read_col(page_index, index, i))
                else:
                    new_record.append(values[i])
        else:
            new_rid = self.base_page[page_index].meta_data.read_INDIRECTION(index)
            self.tail_page[-1].meta_data.write_INDIRECTION(new_rid)
            [new_page_index, new_index] = self.t_locate(new_rid)
            for i in range(0, self.n_columns):
                if values[i] == None:
                    new_record.append(self.t_read_col(new_page_index, new_index, i))
                else:
                    new_record.append(values[i])
        self.tail_page[-1].write(new_record)
        self.base_page[page_index].meta_data.update_SCHEMA(index, 1)
        self.base_page[page_index].meta_data.update_INDIRECTION(index, next_tid)
        
    def b_delete(self, page_index, index):
        ori_rid = self.base_page[page_index].meta_data.read_RID(index)
        self.base_page[page_index].meta_data.update_RID(index, SPECIAL_RID)
        indirection = self.base_page[page_index].meta_data.read_INDIRECTION(index)
        while indirection != ori_rid:
            [new_page_index, new_index] = self.t_locate(indirection)
            self.tail_page[new_page_index].meta_data.update_TID(new_index, SPECIAL_RID)
            indirection = self.tail_page[new_page_index].meta_data.read_INDIRECTION(new_index)