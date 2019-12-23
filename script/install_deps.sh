export MVPOSE_DIR=$PWD
cd $MVPOSE_DIR/backend/tf_cpn/lib/
make

cd ./lib_kernel/lib_nms
bash compile.sh

cd $MVPOSE_DIR/backend/light_head_rcnn/lib/
bash make.sh

cd $MVPOSE_DIR/src/m_lib/
python3 setup.py build_ext --inplace
