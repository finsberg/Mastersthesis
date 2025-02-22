# -*- coding: utf-8 -*-
"""
Created on Thu Sep  9 14:13:48 2021
@author: benda
"""

import numpy as np
from scipy.integrate import odeint
import deepxde as dde
from deepxde.backend import tf
import os
import time
import matplotlib.pyplot as plt

from postprocessing import saveplot



def fitzhugh_nagumo_model(
    t,
    a = -0.3,
    b = 1.4,
    tau = 20,
    Iext = 0.23, #maybe try different init values
    x0 = [0,0] #maybe try different init values
):
    def func(x, t):
        return np.array([x[0] - x[0] ** 3 - x[1] + Iext, (x[0] - a - b * x[1]) / tau])
    
    
    
    return odeint(func, x0, t)



def pinn(data_t, data_y, noise, savename, restore=False, first_num_epochs=int(1e3), sec_num_epochs=int(1e5), display_every=int(1e3)):
    """
    Parameters
    ----------
    data_t : TYPE
        DESCRIPTION.
    data_y : TYPE
        DESCRIPTION.
    noise : TYPE
        DESCRIPTION.
    savename : TYPE
        DESCRIPTION.
    restore : TYPE, optional
        DESCRIPTION. The default is False.
    first_num_epochs : TYPE, optional
        DESCRIPTION. The default is int(1e3).
    sec_num_epochs : TYPE, optional
        DESCRIPTION. The default is int(1e5).
    display_every : TYPE, optional
        DESCRIPTION. The default is 1e3.
    Returns
    -------
    TYPE
        DESCRIPTION.
    """
    
    
    a = tf.math.softplus(tf.Variable(0, trainable=True, dtype=tf.float32)) * .1
    b = tf.math.softplus(tf.Variable(0, trainable=True, dtype=tf.float32))
    tau = tf.math.softplus(tf.Variable(0, trainable=True, dtype=tf.float32)) * 20
    Iext = tf.math.softplus(tf.Variable(0, trainable=True, dtype=tf.float32)) * .1 #try testing different values

    var_list = [a, b, tau, Iext]
    
    def ODE(t, y):
        v1 = y[:, 0:1] - y[:,0:1] ** 3 - y[:, 1:2] + Iext
        v2 =  (y[:, 0:1] - a - b * y[:, 1:2]) / tau
        return [
            tf.gradients(y[:, 0:1], t)[0] - (v1),
            tf.gradients(y[:, 1:2], t)[0] - (v2),
        ]
    
    geom = dde.geometry.TimeDomain(data_t[0, 0], data_t[-1, 0])
    
    
    # Right point
    def boundary(x, _):
        return np.isclose(x[0], data_t[-1, 0])

    y1 = data_y[-1]
    bc0 = dde.DirichletBC(geom, lambda X: y1[0], boundary, component=0)
    bc1 = dde.DirichletBC(geom, lambda X: y1[1], boundary, component=1) #should component be 0 here? Or maybye the init condition
    # bc2 = dde.DirichletBC(geom, lambda X: y1[2], boundary, component=2)
    
    """    
    bc3 = dde.DirichletBC(geom, lambda X: y1[3], boundary, component=3)
    bc4 = dde.DirichletBC(geom, lambda X: y1[4], boundary, component=4)
    bc5 = dde.DirichletBC(geom, lambda X: y1[5], boundary, component=5)
    bc6 = dde.DirichletBC(geom, lambda X: y1[6], boundary, component=6)
    """
    
    # import IPython
    # IPython.embed()
    
    # Observes, or the input data
    n = len(data_t)
    idx = np.append(
        np.random.choice(np.arange(1, n - 1), size=n // 4, replace=False), [0, n - 1]
    )
    # ptset = dde.PointSetBC(data_t[idx])
    ptset = dde.bc.PointSet(data_t[idx]) 
    
    inside = lambda x, _: ptset.inside(x)
    
    observe_y4 = dde.DirichletBC(
        geom, ptset.values_to_func(data_y[idx, 0:1]), inside, component=0
    )
    observe_y5 = dde.DirichletBC(
        geom, ptset.values_to_func(data_y[idx, 1:2]), inside, component=1
    )
    
    
    np.savetxt( os.path.join(savename, "input.dat"), np.hstack((data_t[idx], data_y[idx, 0:1], data_y[idx, 1:2])))

    data = dde.data.PDE( #should this be TimePDE?
        geom,
        ODE,
        # [bc0, bc1, bc2, bc3, bc4, bc5, bc6, observe_y4, observe_y5],
        [bc0, bc1, observe_y4, observe_y5],
        # [],
        anchors=data_t,
    )
    
    #ceate a feed forward network with 3 hidden layers with 128 nodes, using the swish activation function, and
    #to initalize paramaters the glorot_normal_initializeris used
    net = dde.maps.FNN([1] + [128] * 3 + [2], "swish", "Glorot normal")

    def feature_transform(t):
        return tf.concat(
            (
                t,
                tf.sin(t),
                tf.sin(2 * t),
                tf.sin(3 * t),
                tf.sin(4 * t),
                tf.sin(5 * t),
                tf.sin(6 * t),
            ),
            axis=1,
        )

    net.apply_feature_transform(feature_transform) #maybe try without this one
    
    def output_transform(t, y):
        # print( np.shape(data_y[0]), np.shape(t), np.shape([1., 1.]), np.shape(y) )
        return (
            # data_y[0] + tf.math.tanh(t) * tf.constant([1, 1, 0.1, 0.1, 0.1, 1, 0.1]) * y
            data_y[0] + tf.math.tanh(t) * tf.constant([1., 1.]) * y #test different vaules
        )

    net.apply_output_transform(output_transform)

    model = dde.Model(data, net)

    checkpointer = dde.callbacks.ModelCheckpoint(
        # os.path.join(savename,"model/model.ckpt"), verbose=1, save_better_only=True, period=1000
        os.path.join(savename,"model/model.ckpt"), verbose=1, save_better_only=True, period=1000
    )
    variable = dde.callbacks.VariableValue(
        var_list, period=1000, filename=os.path.join(savename,"variables.dat"), precision=3,
    )
    callbacks = [checkpointer, variable]
    
    
    # bc_weights = [1, 1, 10, 10, 10, 1, 10] 
    bc_weights = [1, 1]
    if noise >= 0.1:
        bc_weights = [w * 10 for w in bc_weights]
        
    data_weights = [1, 1]
    # Large noise requires small data_weights
    if noise >= 0.1:
        data_weights = [w / 10 for w in data_weights]
    
    model.compile("adam", lr=1e-3, loss_weights=[0] * 2 + bc_weights + data_weights) #test differnet optimizers
    model.train(epochs=int(first_num_epochs), display_every=int(display_every))
    
    # ode_weights = [1e-3, 1e-3, 1e-2, 1e-2, 1e-2, 1e-3, 1]
    # ode_weights = [1e-3, 1e-3]
    ode_weights = [0, 0]
    # Large noise requires large ode_weights
    if noise > 0:
        ode_weights = [10 * w for w in ode_weights]
    model.compile("adam", lr=1e-3, loss_weights=ode_weights + bc_weights + data_weights)
    
    #if you want to restore from a previous run
    if restore == True:
        #reads form the checkpoint text file
        with open(os.path.join(savename,"model/checkpoint"), 'r') as reader:
            inp = reader.read()
            restore_from = inp.split(" ")[1].split('"')[1]
            
        losshistory, train_state = model.train(
            epochs = int(sec_num_epochs), #int(1e5) if noise == 0 else int(1e5),
            display_every=int(display_every),
            callbacks=callbacks,
            disregard_previous_best=True,
            model_restore_path=os.path.join(savename,"model", restore_from) #add the final epoch number 
        )
    else:
        losshistory, train_state = model.train(
            epochs = int(sec_num_epochs), #int(1e5) if noise == 0 else int(1e5),
            display_every=int(display_every),
            callbacks=callbacks,
            disregard_previous_best=True
        )
    
    # import IPython
    # #breakpoint()
    # IPython.embed()
    saveplot(losshistory, train_state, issave=True, isplot=True, output_dir=savename) 
    # dde.postprocessing.saveplot(losshistory, train_state, issave=True, isplot=True) #wanted to add output_dir=savename but get:
                                                                                    #TypeError: saveplot() got an unexpected keyword argument 'output_dir'
    var_list = [model.sess.run(v) for v in var_list]
    return var_list
    
    


def main():
    start = time.time()
    #t = np.arange(0, 10, 0.005)[:, None]
    noise = 0.
    tf.device("gpu")
    savename = "./fitzhugh_nagumo_res" #make sure that this directory exists
    
    # Data
    
    t = np.linspace(0, 99, 2000)[:, None]
    
    y = fitzhugh_nagumo_model(np.ravel(t))
    
    # plt.plot(t, y[:,0], label="v")
    # plt.plot(t, y[:,1], label="w")
    # plt.legend(loc="best")
    # plt.xlabel("Time (ms)")
    # plt.ylabel("Voltage (mV)")
    # plt.title("Input data")
    # plt.savefig(savename + "/plot_exe.pdf")
    # plt.show()
    # plt.plot(t, y[:,0] + y[:,1], label="v+w")
    # plt.legend(loc="best")
    # plt.show()
    
    # print(t.shape, y.shape)
    
    np.savetxt(os.path.join(savename, "fitzhugh_nagumo.dat"), np.hstack((t, y)))
    # Add noise
    if noise > 0:
        std = noise * y.std(0)
        y[1:-1, :] += np.random.normal(0, std, (y.shape[0] - 2, y.shape[1]))
        np.savetxt(os.path.join(savename, "fitzhugh_nagumo_noise.dat"), np.hstack((t, y)))

    # Train
    var_list = pinn(t, y, noise, savename, restore=False, first_num_epochs=1e3, sec_num_epochs=5e4, display_every=1e3)

    # Prediction
    y_pred = fitzhugh_nagumo_model(np.ravel(t), *var_list)
    np.savetxt(os.path.join(savename, "fitzhugh_nagumo_pred.dat"), np.hstack((t, y_pred)))
    
    print("Shapes: ", t.shape, y_pred.shape, np.shape(var_list))
    
    # plt.plot(t, y_pred[:,0], label="v")
    # plt.plot(t, y_pred[:,1], label="w")
    # plt.legend(loc="best")
    # plt.xlabel("Time (ms)")
    # plt.ylabel("Voltage (mV)")
    # plt.title("Prediction")
    # plt.savefig(savename + "/plot_pred.pdf")
    # plt.show()
    
    # plt.plot(t, y[:,0], label="Exact")
    # plt.plot(t, y_pred[:,0], "r--", label="Learned")
    # plt.legend(loc="best")
    # plt.xlabel("Time (ms)")
    # plt.ylabel("Voltage (mV)")
    # plt.title("Exact vs. Predicted v")
    # plt.savefig(savename + "/plot_comp0.pdf")
    # plt.show()
    
    # plt.plot(t, y[:,1], label="Exact")
    # plt.plot(t, y_pred[:,1], "r--", label="Learned")
    # plt.legend(loc="best")
    # plt.xlabel("Time (ms)")
    # plt.ylabel("Voltage (mV)")
    # plt.title("Exact vs. Predicted w")
    # plt.savefig(savename + "/plot_comp1.pdf")
    # plt.show()
    
    # plt.plot(y_pred[:,0], y_pred[:,1], label="v against w")
    # # plt.legend(loc="best")
    # plt.ylabel("w (mA)")
    # plt.xlabel("v (mV)")
    # plt.title("Phase space of the FitzHugh–Nagumo model")
    # plt.savefig(savename + "/plot_pha.pdf")
    # plt.show()
    
    print(var_list)

    print("\n\nTotal runtime: {}".format(time.time() - start))

if __name__ == "__main__":
    main()