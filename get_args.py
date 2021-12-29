import os
import argparse
import datetime
from random import choice

from utils import create_folder, prepare_folder

class Args:
    def __init__(self):
        self.args = self.parse_arguments()

    def parse_arguments(self):
        parser = argparse.ArgumentParser(); 

        #---# Time #---#
        now = datetime.datetime.now()
        parser.add_argument('--date', default=now.strftime('%Y-%m-%d'), help="Please do not enter any value.")
        parser.add_argument('--time', default=now.strftime('%H:%M:%S'), help="Please do not enter any value.")

        #---# Mode #---#
        parser.add_argument("--mode", default="train", choices=["train", "test"])
        # parser.add_argument("--mode", default="train", choices=["train", "test"])
        parser.add_argument("--seed", default=1004, type=int)

        #---# Model #---#
        parser.add_argument("--model", type=str, default="EEGNet") #DeepConvNet, ShallowConvNet, EEGNet

        #---# Path #---#
        parser.add_argument("--path", type=str, default='/opt/workspace/xohyun/MS/Files_scale/')
        parser.add_argument("--param_path", type=str, default="/opt/workspace/xohyun/MS/param")
        parser.add_argument("--runs_path", type=str, default="/opt/workspace/xohyun/MS/runs")
        parser.add_argument("--save_path", type=str, default="/opt/workspace/xohyun/MS/train/")
        parser.add_argument("--load_path", type=str, default="/opt/workspace/xohyun/MS/train/")

        #---# Train #---#

        # Try several things at once
        # parser.add_argument("--lr_list", type=list, default=[1e-5, 1e-4, 1e-3])     #[1e-5, 1e-4, 1e-3]
        # parser.add_argument("--wd_list", type=list, default=[1e-5, 1e-4, 1e-3])     #[1e-5, 1e-4, 1e-3]
        parser.add_argument("--n_queries", type=int, default=150)

        parser.add_argument("--lr", type=float, default=1e-3)
        parser.add_argument("--wd", type=float, default=1e-3)

        parser.add_argument('--scheduler', '-sch')
        if parser.parse_known_args()[0].scheduler == 'exp':
            parser.add_argument('--gamma', type=float, required=True)
        elif parser.parse_known_args()[0].scheduler == 'step':
            parser.add_argument('--step_size', type=int, required=True, default=1000)
            parser.add_argument('--gamma', type=float, required=True, default=0.1)
        elif parser.parse_known_args()[0].scheduler == 'multi_step':
            parser.add_argument('--milestones', required=True) # type=str2list_int
            parser.add_argument('--gamma', type=float, required=True)
        elif parser.parse_known_args()[0].scheduler == 'plateau':
            parser.add_argument('--factor', type=float, required=True)
            parser.add_argument('--patience', type=int, required=True)
        elif parser.parse_known_args()[0].scheduler == 'cosine':
            parser.add_argument('--T_max', type=float, help='Max iteration number')
            parser.add_argument('--eta_min', type=float, help='minimum learning rate')

        parser.add_argument("--criterion", type=str, default="CEE")
        parser.add_argument("--optimizer", type=str, default="SGD") #AdamW

        parser.add_argument("--metrics", type=list, default=["loss", "acc"])

        parser.add_argument("--batch_size", type=int, default=32)              #512
        parser.add_argument("--epoch", type=int, default=100)                 #3000
        parser.add_argument("--one_bundle", type=int, default=int(1500/2))
        parser.add_argument("--channel_num", type=int, default=28)
        parser.add_argument("--class_num", type=int, default=3)
        parser.add_argument("--expt", type=int, default=1, help="1:오전,2:오후")
        if parser.parse_known_args()[0].expt == 1:
            parser.add_argument("--remove_subj", type=list, default=[1,2,4,14,16,17,19])
        else:
            parser.add_argument("--remove_subj", type=list, default=[4,8,11,17]) 
        parser.add_argument("--test_subj", type=int, default=18)
        parser.add_argument("--test_size", type=float, default=0.5); # 0.05
        # parser.add_argument("-")
    
        #---# Device #---#
        parser.add_argument('--device', default=2, help="cpu or gpu number")

        args = parser.parse_args()

        return args

    def set_save_path(self):
        # if self.args.mode == "train":
        #     create_folder(self.args.save_path)
        create_folder(self.args.save_path)
        # sub_dir = len(os.listdir(self.args.save_path)) + 1
        # dir_name = os.path.join(self.args.save_path, str(sub_dir), str(self.args.test_subj))
        
        dir_name = os.path.join(self.args.save_path, str(self.args.test_subj))

        if self.args.mode == "train":
            prepare_folder([dir_name])
        self.args.save_path = dir_name
        print(f"=== save_path : [{self.args.save_path}] ===")

    def get_load_path(self):
        self.args.load_path = os.path.join(self.args.load_path, str(self.args.test_subj))