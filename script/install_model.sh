export MVPOSE_DIR=$PWD
# require mvpose_model path
mkdir -p $MVPOSE_DIR/backend/CamStyle/logs/
ln -s $mvpose_model/market-ide-camstyle-re $MVPOSE_DIR/backend/CamStyle/logs/

ln -s $mvpose_model/output $MVPOSE_DIR/backend/light_head_rcnn/
ln -s $mvpose_model/log $MVPOSE_DIR/backend/tf_cpn/
